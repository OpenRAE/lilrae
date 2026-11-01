"""Declared cleanup effects and evidence beneath the shared RAES trial lifecycle."""

from dataclasses import replace
from graphlib import TopologicalSorter
import hashlib

import rfc8785
from raes_backend_protocols.capabilities import CleanupCapabilities
from raes_contracts.contracts import (
    CleanupObligationModel,
    CleanupObligationResultModel,
    TrialCleanupPlanModel,
    TrialCleanupReceiptModel,
    validate_trial_cleanup_receipt,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_contracts.trial_unit import TrialUnitRequest
from raes_runtime.runtime_trial_services import TrialCleanupObservation

from aptl.backends.cleanup_evidence import (
    load_cleanup_receipt,
    retain_cleanup_readback,
    verify_cleanup_record,
)
from aptl.core.cleanup import CleanupOwner, CleanupReadback
from aptl.core.correlation.clock import ClockProvider
from aptl.core.runstore import LocalRunStore

CLEANUP_CAPABILITIES = CleanupCapabilities(
    name="native-receipt-cleanup",
    supported_contract_versions=frozenset(
        {"trial-cleanup-plan-v1", "trial-cleanup-receipt-v1"}
    ),
    supported_action_kinds=frozenset({"destroy", "verify"}),
    supported_verification_methods=frozenset({"native-absence"}),
    supports_residual_state_disclosure=True,
)
_TRIGGERS = {
    "succeeded": "success",
    "failed": "failure",
    "cancelled": "cancellation",
    "timed-out": "timeout",
    "aborted": "abort",
}


class DeclaredCleanup:
    """One immutable admitted plan bound to its installed native owner.

    A trial-services composition delegates admission, cleanup and cleanup
    verification here. RAES retains all trial progression and retry authority.
    """

    def __init__(
        self,
        plan: TrialCleanupPlanModel,
        native: CleanupOwner,
        store: LocalRunStore,
        clock: ClockProvider,
    ) -> None:
        self._plan_bytes = plan.model_dump_json()
        self.native, self.store, self.clock = native, store, clock
        self._binding = replace(native.binding)
        self._validate_plan()

    @property
    def plan(self) -> TrialCleanupPlanModel:
        return TrialCleanupPlanModel.model_validate_json(self._plan_bytes)

    def _validate_plan(self) -> None:
        plan, scope = self.plan, self._binding
        if (plan.plan_entry_id, plan.run_id) != (scope.plan_entry_id, scope.run_id):
            raise ValueError("cleanup plan does not match its native binding")
        if set(plan.resource_boundaries) != {scope.boundary_id}:
            raise ValueError("cleanup requires an exact complete attempt boundary")
        boundary = plan.resource_boundaries[scope.boundary_id]
        if (
            boundary.resource_kind != "range-instance"
            or boundary.owner_ref != scope.owner_ref
            or set(boundary.resource_refs) != set(scope.resource_refs)
            or plan.clean_state.mode not in {"fresh", "fresh-range-required"}
        ):
            raise ValueError("cleanup boundary is not supported by the native binding")
        if plan.retry_policy.max_attempts != 1:
            raise ValueError("cleanup retry preparation is not installed")
        probes = [*plan.clean_state.verification_probe_refs]
        for obligation in plan.cleanup_obligations.values():
            probes.extend(obligation.verification_probe_refs)
            if obligation.requirement == "required" and not self._supported(obligation):
                raise ValueError("required cleanup semantics are unsupported")
        if any(probe != f"native-absence:{scope.boundary_id}" for probe in probes):
            raise ValueError("cleanup probe is not bound to the native boundary")

    @staticmethod
    def _supported(obligation: CleanupObligationModel) -> bool:
        return (
            obligation.action_kind in {"destroy", "verify"}
            and obligation.idempotency == "idempotent"
            and obligation.action_profile_ref is None
            and not obligation.compensation_refs
        )

    def admit(self, request: TrialUnitRequest) -> None:
        """Check exact sealed identity without running a native operation."""
        request = replace(request)
        if (
            request.cleanup_plan != self.plan
            or request.execution_attempt_id != self._binding.execution_attempt_id
        ):
            raise ValueError("cleanup request differs from its installed binding")
        self._check_binding()

    def _check_binding(self) -> None:
        if self.native.binding != self._binding:
            raise ValueError("native cleanup binding changed")

    def execute(self, outcome: str) -> TrialCleanupObservation:
        """Execute owed obligations; persist honest partial results before return."""
        self._check_binding()
        if outcome not in _TRIGGERS:
            raise ValueError("cleanup trial outcome is invalid")
        with self.store.finalization_lock(self.plan.run_id):
            intent_id = hashlib.sha256(
                self._binding.execution_attempt_id.encode()
            ).hexdigest()
            self.store.create_run_json_once(
                self.plan.run_id,
                f"cleanup/intents/{intent_id}.json",
                {
                    "plan": self.plan.model_dump(mode="json"),
                    "execution_attempt_id": self._binding.execution_attempt_id,
                    "native_attempt_id": self._binding.native_attempt_id,
                },
            )
            return self._execute_owned(outcome)

    def _execute_owned(self, outcome: str) -> TrialCleanupObservation:
        trigger = _TRIGGERS[outcome]
        plan = self.plan
        results: dict[str, CleanupObligationResultModel] = {}
        evidence = []
        interrupted: BaseException | None = None
        publication_failure: Exception | None = None
        order = TopologicalSorter(
            {key: value.depends_on for key, value in plan.cleanup_obligations.items()}
        )
        for key in order.static_order():
            obligation = plan.cleanup_obligations[key]
            if trigger not in obligation.triggers:
                continue
            failed_dependency = any(
                parent not in results or results[parent].status != "succeeded"
                for parent in obligation.depends_on
            )
            try:
                readback, status = self._perform(
                    obligation, failed_dependency or interrupted is not None
                )
            except BaseException as exc:
                # Preserve the interrupted attempt, then propagate the original
                # interruption after publication. No later native effect runs.
                interrupted = exc
                readback, status = (
                    CleanupReadback((), ("native-cleanup-interrupted",)),
                    "unverified",
                )
            try:
                record = retain_cleanup_readback(
                    self.store, self.clock, self._binding, key, readback
                )
            except Exception as exc:
                # Losing evidence must block success and dependent effects,
                # but must not prevent independent safe cleanup obligations.
                if publication_failure is None:
                    publication_failure = exc
                continue
            evidence.append(record)
            results[key] = CleanupObligationResultModel(
                obligation_id=key,
                status=status,
                evidence_refs=[record.evidence_record_id],
                residual_state_refs=[]
                if status == "succeeded"
                else [f"residual:{self._binding.boundary_id}"],
            )
        if publication_failure is not None:
            if interrupted is not None:
                raise interrupted from publication_failure
            raise publication_failure
        status = (
            "not-required"
            if not results
            else (
                "succeeded"
                if all(result.status == "succeeded" for result in results.values())
                else "failed"
            )
        )
        receipt_data = {
            "cleanup_plan_ref": plan.plan_id,
            "plan_entry_id": plan.plan_entry_id,
            "run_id": plan.run_id,
            "execution_attempt_id": self._binding.execution_attempt_id,
            "trial_outcome": outcome,
            "cleanup_status": status,
            "obligation_results": {
                key: result.model_dump(mode="json") for key, result in results.items()
            },
        }
        if status == "succeeded" and plan.clean_state.mode == "fresh":
            receipt_data["clean_state_claim"] = {
                "disposition": "verified-clean",
                "boundary_refs": [self._binding.boundary_id],
                "evidence_refs": [record.evidence_record_id for record in evidence],
            }
        receipt_id = (
            "cleanup-" + hashlib.sha256(rfc8785.dumps(receipt_data)).hexdigest()
        )
        receipt = TrialCleanupReceiptModel(receipt_id=receipt_id, **receipt_data)
        validate_trial_cleanup_receipt(plan, receipt)
        self.store.create_run_json_once(
            plan.run_id,
            f"cleanup/receipts/{receipt_id}.json",
            receipt.model_dump(mode="json"),
        )
        if interrupted is not None:
            raise interrupted
        return TrialCleanupObservation(
            receipt=receipt, evidence=tuple(evidence), idempotent_effects=True
        )

    def _perform(
        self, obligation: CleanupObligationModel, failed_dependency: bool
    ) -> tuple[CleanupReadback, str]:
        if failed_dependency:
            return CleanupReadback((), ("cleanup-dependency-unverified",)), "unverified"
        if not self._supported(obligation):
            return CleanupReadback((), ("cleanup-action-unsupported",)), "unsupported"
        try:
            readback = self.native.execute(
                obligation.action_kind, obligation.timeout_seconds
            )
        except OSError, TimeoutError, ValueError:
            readback = CleanupReadback((), ("native-cleanup-unavailable",))
        return readback, "succeeded" if readback.absent else "failed"

    def cleanup(
        self,
        request: TrialUnitRequest,
        outcome: str,
        snapshot: RuntimeSnapshot,
    ) -> tuple[ApplyResult, TrialCleanupObservation]:
        """The released TrialRuntimeServices cleanup call shape."""
        self.admit(request)
        observation = self.execute(outcome)
        # The call succeeded in producing a verified receipt. A failed cleanup
        # remains a failed receipt; RAES must retain that terminal evidence.
        return ApplyResult(success=True, snapshot=snapshot), observation

    def verify_observation(self, observation: TrialCleanupObservation) -> None:
        """Verify stored bytes and live absence before accepting a clean result."""
        self._check_binding()
        validate_trial_cleanup_receipt(self.plan, observation.receipt)
        stored_receipt = load_cleanup_receipt(
            self.store, self.plan.run_id, observation.receipt.receipt_id
        )
        if stored_receipt != observation.receipt:
            raise ValueError("cleanup receipt differs from retained evidence")
        if (
            observation.receipt.execution_attempt_id
            != self._binding.execution_attempt_id
        ):
            raise ValueError("cleanup evidence belongs to another attempt")
        records = {record.evidence_record_id: record for record in observation.evidence}
        for record in records.values():
            if record.run_ref.ref_id != self.plan.run_id:
                raise ValueError("cleanup evidence belongs to another run")
            verify_cleanup_record(self.store, record)
        for result in observation.receipt.obligation_results.values():
            if not set(result.evidence_refs) <= set(records):
                raise ValueError("cleanup receipt evidence is missing")
        if observation.receipt.cleanup_status == "succeeded":
            timeout = max(
                item.timeout_seconds for item in self.plan.cleanup_obligations.values()
            )
            if not self.native.execute("verify", timeout).absent:
                raise ValueError("native cleanup absence is no longer verified")
