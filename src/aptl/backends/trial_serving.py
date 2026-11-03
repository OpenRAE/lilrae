"""Placement and isolation around one already admitted RAES runtime trial unit."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
import hashlib
import os
from pathlib import Path

import rfc8785
from raes_backend_protocols.trial_unit import BackendTrialUnit
from raes_contracts.contracts.trial_replacement_archive import (
    replacement_resources_reusable,
)
from raes_contracts.trial_unit import (
    TrialUnitRequest,
    TrialUnitResult,
    validate_trial_unit_result,
)
from raes_runtime import RuntimeControlPlane
from raes_runtime.experiment_records import (
    ExperimentEvidenceReader,
    ExperimentRecordArchive,
    ExperimentRecordBundle,
    ExperimentRunMetadata,
)
from raes_runtime.runtime_trial_services import TrialCleanupObservation
from raes_runtime.runtime_trial_unit import TrialPending

from aptl.backends.cleanup import DeclaredCleanup
from aptl.core.deployment.docker_compose import DockerComposeBackend
from aptl.core.deployment.errors import BackendTimeoutError
from aptl.core.deployment._compose_resource_ownership import OwnershipConflictError
from aptl.core.deployment.lilrae_native_evidence import confirm_native_absence
from aptl.core.lifecycle_guard import (
    canonical_lifecycle_project_root,
    lifecycle_mutation_lock,
    placement_mutation_lock,
)
from aptl.core.trial_ownership import (
    TRIAL_FENCE,
    claim_trial_owner,
    require_trial_owner,
    trial_fence_owner,
)
from aptl.utils.pathsafe import (
    PathContainmentError,
    open_private_dir_contained_nofollow,
    remove_contained_nofollow,
)


@dataclass(frozen=True)
class DockerTrialPlacement:
    """The approved backend and shared state root, supplied by the operator."""

    backend: DockerComposeBackend
    state_root: Path

    def daemon_id(self) -> str:
        identity = self.backend.daemon_identity()
        if not identity:
            raise ValueError("trial-daemon-unverified")
        return identity

    def require_clean(self) -> None:
        """Include stopped containers, volumes and direct native realizations."""
        presence = self.backend.observe_project_runtime()
        if (
            presence.error
            or presence.present
            or self.backend._scoped_compose_volume_names()
        ):
            raise ValueError("trial-placement-contaminated")
        ownership = self.backend._load_resource_ownership()
        if ownership is not None:
            for kind in ("container", "network", "volume"):
                for receipt in ownership.receipts(kind):
                    if not confirm_native_absence(self.backend, receipt):
                        raise ValueError("trial-placement-contaminated")


@dataclass(frozen=True)
class TrialOutcomeReporting:
    """Bind partial and terminal reporting to the admitted runtime and owners."""

    runtime: RuntimeControlPlane
    experiment_id: str
    metadata: Callable[
        [TrialUnitRequest, TrialUnitResult | None], Mapping[str, ExperimentRunMetadata]
    ]
    identity: object | None = None
    evidence_reader: ExperimentEvidenceReader | None = None
    archive: ExperimentRecordArchive | None = None

    def report(
        self, request: TrialUnitRequest, result: TrialUnitResult | None
    ) -> ExperimentRecordBundle:
        bundle = report_trial_outcomes(
            self.runtime,
            self.experiment_id,
            metadata=self.metadata(request, result),
            identity=self.identity,
            evidence_reader=self.evidence_reader,
            archive=self.archive,
        )
        for run in bundle.runs:
            accounting = run.execution_accounting
            if (
                run.run_id == request.run_id
                and accounting is not None
                and accounting.plan_digest == request.plan.plan_digest
                and accounting.plan_entry_id == request.plan_entry_id
                and accounting.attempts[-1].execution_attempt_id
                == request.execution_attempt_id
            ):
                return bundle
        raise ValueError("trial-reporting-identity-mismatch")


@dataclass(frozen=True)
class LilraeTrialUnit:
    """Serve one request through its RAES unit; never allocate or resume a plan.

    ``runtime_unit`` must be the unit already bound by the shared runtime to
    this request and its durable ledger. Repeated delivery reconciles that
    ledger; this wrapper supplies no retry or cancellation policy.
    """

    runtime_unit: BackendTrialUnit
    cleanup: DeclaredCleanup
    placement: DockerTrialPlacement
    target_scope: str
    reporting: TrialOutcomeReporting
    max_operations: int = 4096
    max_attempt_seconds: int = 86400

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 1
            for value in (self.max_operations, self.max_attempt_seconds)
        ):
            raise ValueError("trial-serving-limits-invalid")

    def execute_trial(self, request: TrialUnitRequest) -> TrialUnitResult:
        """Retain unknown effects and expose only bounded owner failure codes."""
        try:
            return self._execute_trial(request)
        except (
            PathContainmentError,
            OSError,
            BackendTimeoutError,
            OwnershipConflictError,
        ):
            raise ValueError("trial-serving-owner-unavailable") from None

    def _execute_trial(self, request: TrialUnitRequest) -> TrialUnitResult:
        request = replace(request)
        self._admit(request)
        project = self.cleanup.native.binding.project_dir
        daemon = self.placement.daemon_id()
        daemon_root = (
            self.placement.state_root / hashlib.sha256(daemon.encode()).hexdigest()
        )
        # The operator provides one existing shared root for this placement.
        # The normal lifecycle lock creates its private child state safely.
        fd = open_private_dir_contained_nofollow(
            self.placement.state_root, Path(daemon_root.name)
        )
        os.close(fd)
        owner = (
            hashlib.sha256(
                rfc8785.dumps(
                    {
                        "project": str(project.resolve()),
                        "plan": request.plan.plan_digest,
                        "entry": request.plan_entry_id,
                        "attempt": request.execution_attempt_id,
                        "snapshot": request.instantiated_sdl_digest,
                    }
                )
            )
            .hexdigest()
            .encode("ascii")
        )
        with (
            placement_mutation_lock(daemon_root, trial_owner=owner),
            lifecycle_mutation_lock(project, trial_owner=owner),
        ):
            if self.placement.daemon_id() != daemon:
                raise ValueError("trial-daemon-changed")
            require_trial_owner(daemon_root, owner)
            if (
                trial_fence_owner(project) is None
                and trial_fence_owner(daemon_root) is None
            ):
                self.placement.require_clean()
            claim_trial_owner(project, owner)
            claim_trial_owner(daemon_root, owner)
            return self._execute_owned(request, daemon_root, project, daemon)

    def _admit(self, request: TrialUnitRequest) -> None:
        if os.name != "posix":
            raise ValueError("trial-serving-posix-required")
        count = sum(
            len(plan.operations)
            for plan in (
                request.provisioning_plan,
                request.orchestration_plan,
                request.evaluation_plan,
            )
        )
        if count > self.max_operations or (
            request.execution_controls.attempt_timeout_seconds
            > self.max_attempt_seconds
        ):
            raise ValueError("trial-serving-resource-limit")
        self.cleanup.admit(request)
        project = self.cleanup.native.binding.project_dir.resolve()
        if (
            project != self.placement.backend.project_dir.resolve()
            or project != canonical_lifecycle_project_root(project)
        ):
            raise ValueError("trial-placement-project-mismatch")

    def _execute_owned(
        self, request: TrialUnitRequest, daemon_root: Path, project: Path, daemon: str
    ) -> TrialUnitResult:
        # The runtime owns cessation, partial capture and owed cleanup, including
        # when this call raises TrialPending. Never tear down an unknown effect
        # independently or clear a fence in a finally clause.
        try:
            result = replace(self.runtime_unit.execute_trial(request))
        except TrialPending:
            if self.placement.daemon_id() != daemon:
                raise ValueError("trial-daemon-changed") from None
            # A started attempt can have reportable facts without a terminal
            # result. RAE's producer preserves uncertainty and absent phases.
            self.reporting.report(request, None)
            raise
        if self.placement.daemon_id() != daemon:
            raise ValueError("trial-daemon-changed")
        validate_trial_unit_result(request, result, target_scope=self.target_scope)
        self.cleanup.verify_observation(
            TrialCleanupObservation(
                receipt=result.cleanup_receipt, evidence=result.cleanup_evidence
            )
        )
        self.cleanup.store.create_run_json_once(
            request.run_id,
            "trial-serving/handoff.json",
            {
                "run_id": request.run_id,
                "plan_id": request.plan.plan_id,
                "plan_digest": request.plan.plan_digest,
                "entry_digest": request.plan.entries[
                    request.plan_entry_id
                ].entry_digest,
                "instantiated_sdl_digest": request.instantiated_sdl_digest,
                "plan_entry_id": request.plan_entry_id,
                "execution_attempt_id": request.execution_attempt_id,
                "cleanup_receipt_id": result.cleanup_receipt.receipt_id,
                "evidence_record_refs": [
                    record.evidence_record_id for record in result.evidence
                ],
                "cleanup_evidence_record_refs": [
                    record.evidence_record_id for record in result.cleanup_evidence
                ],
            },
        )
        self.reporting.report(request, result)
        if replacement_resources_reusable(request.cleanup_plan, result.cleanup_receipt):
            remove_contained_nofollow(project, TRIAL_FENCE)
            remove_contained_nofollow(daemon_root, TRIAL_FENCE)
        return result


def report_trial_outcomes(
    runtime: RuntimeControlPlane,
    experiment_id: str,
    *,
    metadata: Mapping[str, ExperimentRunMetadata],
    identity: object | None = None,
    evidence_reader: ExperimentEvidenceReader | None = None,
    archive: ExperimentRecordArchive | None = None,
) -> ExperimentRecordBundle:
    """Report retained trials through the shared producer and its validators.

    Trusted composition supplies evaluator facts, not inferred success. The
    returned sources preserve participant histories and partial evidence. Run
    state, invalidation, validation and replacement eligibility remain RAES-owned.
    An absent reader/archive leaves an inspectable bundle, not a sealed record.
    """
    return runtime.experiment_records(
        experiment_id,
        identity=identity,
        metadata=metadata,
        evidence_reader=evidence_reader,
        archive=archive,
    )
