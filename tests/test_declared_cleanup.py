"""Declared cleanup uses released receipt semantics and retained native facts."""

from dataclasses import replace
from pathlib import Path
import json

import pytest
from raes_contracts.contracts import (
    TrialCleanupPlanModel,
    validate_trial_cleanup_receipt,
)

from aptl.backends.cleanup import DeclaredCleanup
from aptl.core.cleanup import CleanupBinding, CleanupReadback, CleanupResourceState
from aptl.core.correlation.clock import FixedClockProvider
from aptl.core.runstore import LocalRunStore, SealedRunError


def cleanup_plan() -> TrialCleanupPlanModel:
    return TrialCleanupPlanModel.model_validate(
        {
            "plan_id": "cleanup-a",
            "plan_entry_id": "entry-a",
            "run_id": "run-a",
            "clean_state": {
                "mode": "fresh-range-required",
                "boundary_refs": ["range-a"],
            },
            "resource_boundaries": {
                "range-a": {
                    "boundary_id": "range-a",
                    "resource_kind": "range-instance",
                    "owner_ref": "apparatus:range-a",
                    "resource_refs": ["node.a"],
                }
            },
            "cleanup_obligations": {
                "destroy": {
                    "obligation_id": "destroy",
                    "boundary_refs": ["range-a"],
                    "action_kind": "destroy",
                    "triggers": [
                        "success",
                        "failure",
                        "cancellation",
                        "timeout",
                        "abort",
                    ],
                    "requirement": "required",
                    "idempotency": "idempotent",
                    "verification_probe_refs": ["native-absence:range-a"],
                    "timeout_seconds": 120,
                }
            },
            "retry_policy": {"max_attempts": 1, "after_effect_policy": "disallow"},
        }
    )


class NativeOwner:
    def __init__(self, project_dir: Path) -> None:
        self.binding = CleanupBinding(
            plan_entry_id="entry-a",
            run_id="run-a",
            execution_attempt_id="exec-a",
            native_attempt_id="native-a",
            boundary_id="range-a",
            owner_ref="apparatus:range-a",
            resource_refs=("node.a",),
            project_dir=project_dir,
        )
        self.calls: list[tuple[str, int]] = []
        self.state = "present"
        self.fail = False

    def execute(self, action: str, timeout_seconds: int) -> CleanupReadback:
        self.calls.append((action, timeout_seconds))
        if action == "destroy" and not self.fail:
            self.state = "absent"
        return CleanupReadback(
            resources=(CleanupResourceState("container", "a" * 64, self.state),),
            reasons=("native-remove-failed",) if self.fail else (),
        )


def service(tmp_path: Path) -> tuple[DeclaredCleanup, NativeOwner]:
    native = NativeOwner(tmp_path)
    store = LocalRunStore(tmp_path / "runs")
    store.create_run("run-a")
    return DeclaredCleanup(
        cleanup_plan(),
        native,
        store,
        FixedClockProvider(measurement_time="2026-11-01T10:00:00Z"),
    ), native


@pytest.mark.parametrize(
    "outcome", ["succeeded", "failed", "cancelled", "timed-out", "aborted"]
)
def test_terminal_triggers_keep_execution_and_cleanup_outcomes_separate(
    tmp_path, outcome
):
    cleanup, native = service(tmp_path)
    observation = cleanup.execute(outcome)
    receipt = observation.receipt
    validate_trial_cleanup_receipt(cleanup_plan(), receipt)
    assert receipt.trial_outcome == outcome
    assert receipt.cleanup_status == "succeeded"
    assert receipt.execution_attempt_id == "exec-a"
    assert receipt.run_id == "run-a"
    assert native.calls[0] == ("destroy", 120)
    assert receipt.obligation_results["destroy"].evidence_refs
    cleanup.verify_observation(observation)


def test_failed_cleanup_retains_residual_evidence_without_a_clean_claim(tmp_path):
    cleanup, native = service(tmp_path)
    native.fail = True
    observation = cleanup.execute("succeeded")
    validate_trial_cleanup_receipt(cleanup_plan(), observation.receipt)
    assert observation.receipt.cleanup_status == "failed"
    assert observation.receipt.trial_outcome == "succeeded"
    assert observation.receipt.clean_state_claim is None
    assert observation.receipt.obligation_results["destroy"].residual_state_refs
    cleanup.verify_observation(observation)


def test_foreign_attempt_binding_is_refused_before_native_effects(tmp_path):
    cleanup, native = service(tmp_path)
    native.binding = replace(native.binding, run_id="other-run")
    with pytest.raises(ValueError):
        cleanup.execute("succeeded")
    assert native.calls == []


def test_required_unsupported_action_is_refused_before_effects(tmp_path):
    cleanup, native = service(tmp_path)
    plan = cleanup_plan().model_dump(mode="json")
    plan["cleanup_obligations"]["destroy"]["action_kind"] = "reset"
    with pytest.raises(ValueError):
        DeclaredCleanup(
            TrialCleanupPlanModel.model_validate(plan),
            native,
            cleanup.store,
            cleanup.clock,
        )
    assert native.calls == []


def test_sealed_archive_is_refused_before_native_effects(tmp_path):
    cleanup, native = service(tmp_path)
    cleanup.store.commit_seal_marker("run-a", {"sealed": True})
    with pytest.raises(SealedRunError):
        cleanup.execute("succeeded")
    assert native.calls == []


def test_interruption_retains_an_unverified_receipt_then_propagates(tmp_path):
    cleanup, native = service(tmp_path)

    def interrupt(action, timeout_seconds):
        raise KeyboardInterrupt

    native.execute = interrupt
    with pytest.raises(KeyboardInterrupt):
        cleanup.execute("cancelled")
    receipts = list(
        (cleanup.store.get_run_path("run-a") / "cleanup/receipts").glob("*.json")
    )
    assert len(receipts) == 1
    from raes_contracts.contracts import TrialCleanupReceiptModel

    receipt = TrialCleanupReceiptModel.model_validate_json(receipts[0].read_bytes())
    assert receipt.cleanup_status == "failed"
    assert receipt.obligation_results["destroy"].status == "unverified"


def test_dependency_failure_keeps_independent_work_but_prevents_dependent_effects(
    tmp_path,
):
    cleanup, native = service(tmp_path)
    plan = cleanup_plan().model_dump(mode="json")
    original = plan["cleanup_obligations"]["destroy"]
    plan["cleanup_obligations"]["dependent"] = {
        **original,
        "obligation_id": "dependent",
        "depends_on": ["destroy"],
    }
    plan["cleanup_obligations"]["independent"] = {
        **original,
        "obligation_id": "independent",
    }
    native.fail = True
    cleanup = DeclaredCleanup(
        TrialCleanupPlanModel.model_validate(plan), native, cleanup.store, cleanup.clock
    )
    result = cleanup.execute("failed")
    assert len(native.calls) == 2
    assert result.receipt.obligation_results["dependent"].status == "unverified"
    validate_trial_cleanup_receipt(cleanup.plan, result.receipt)


def test_changed_receipt_cannot_reuse_an_existing_evidence_reference(tmp_path):
    cleanup, native = service(tmp_path)
    observed = cleanup.execute("succeeded")
    changed = observed.model_copy(
        update={
            "receipt": observed.receipt.model_copy(update={"trial_outcome": "failed"})
        }
    )
    with pytest.raises(ValueError):
        cleanup.verify_observation(changed)


def test_invalid_outcome_is_refused_before_any_archive_or_native_effect(tmp_path):
    cleanup, native = service(tmp_path)
    with pytest.raises(ValueError):
        cleanup.execute("not-a-trial-outcome")
    assert native.calls == []
    assert not (cleanup.store.get_run_path("run-a") / "cleanup").exists()


def test_cleanup_receipt_is_consumable_by_the_public_batch_validator(tmp_path):
    from raes_contracts.corpus import corpus_root
    from raes_contracts.contracts import (
        AdmittedTrialPlanModel,
        BatchExecutionReceiptModel,
        seal_admitted_trial_plan,
        validate_batch_execution_receipt,
    )

    root = corpus_root() / "fixtures"
    original = AdmittedTrialPlanModel.model_validate_json(
        (root / "plans/admitted-trial-plan-v1/valid/minimal.json").read_bytes()
    )
    cleanup, native = service(tmp_path)
    fields = {
        name: getattr(original, name)
        for name in type(original).model_fields
        if name != "plan_digest"
    }
    fields["cleanup_plans"] = {"cleanup-a": cleanup.plan}
    plan = seal_admitted_trial_plan(**fields)
    observed = cleanup.execute("failed")
    payload = json.loads(
        (
            root / "control-plane/batch-execution-receipt-v1/valid/serial.json"
        ).read_bytes()
    )
    payload.update(
        plan_id=plan.plan_id,
        plan_digest=plan.plan_digest,
        execution_attempt_id=observed.receipt.execution_attempt_id,
        trial_outcome=observed.receipt.trial_outcome,
        cleanup_receipt_ref=observed.receipt.receipt_id,
    )
    batch = BatchExecutionReceiptModel.model_validate(payload)
    validate_batch_execution_receipt(plan, batch, cleanup_receipt=observed.receipt)
    with pytest.raises(ValueError):
        validate_batch_execution_receipt(
            plan,
            batch.model_copy(update={"execution_attempt_id": "foreign"}),
            cleanup_receipt=observed.receipt,
        )


def test_cleanup_capability_is_declared_only_for_an_installed_service():
    from aptl.backends.cleanup import CLEANUP_CAPABILITIES
    from aptl.backends.raes_manifest import create_aptl_manifest
    from raes_backend_protocols.capability_admission import (
        require_cleanup_plan_capability,
    )
    from raes_backend_protocols.manifest import backend_manifest_v2_model

    assert create_aptl_manifest().cleanup is None
    manifest = create_aptl_manifest(cleanup=CLEANUP_CAPABILITIES)
    require_cleanup_plan_capability(manifest, cleanup_plan())
    payload = backend_manifest_v2_model(manifest)
    assert payload.capabilities.cleanup.supported_action_kinds == ["destroy", "verify"]
    assert not payload.capabilities.cleanup.supports_reusable_state


def test_verified_fresh_cleanup_has_only_a_scope_bounded_clean_claim(tmp_path):
    cleanup, native = service(tmp_path)
    payload = cleanup.plan.model_dump(mode="json")
    payload["clean_state"] = {
        "mode": "fresh",
        "boundary_refs": ["range-a"],
        "verification_probe_refs": ["native-absence:range-a"],
    }
    cleanup = DeclaredCleanup(
        TrialCleanupPlanModel.model_validate(payload),
        native,
        cleanup.store,
        cleanup.clock,
    )
    receipt = cleanup.execute("succeeded").receipt
    assert receipt.clean_state_claim.disposition == "verified-clean"
    assert receipt.clean_state_claim.boundary_refs == ["range-a"]


def test_compensation_references_are_rejected_before_effects(tmp_path):
    cleanup, native = service(tmp_path)
    payload = cleanup.plan.model_dump(mode="json")
    payload["cleanup_obligations"]["destroy"]["compensation_refs"] = [
        "compensation:unknown"
    ]
    with pytest.raises(ValueError):
        DeclaredCleanup(
            TrialCleanupPlanModel.model_validate(payload),
            native,
            cleanup.store,
            cleanup.clock,
        )
    assert not native.calls


def test_publication_failure_does_not_suppress_independent_destruction(
    tmp_path, monkeypatch
):
    cleanup, native = service(tmp_path)
    payload = cleanup.plan.model_dump(mode="json")
    original = payload["cleanup_obligations"]["destroy"]
    payload["cleanup_obligations"] = {
        "verify": {**original, "obligation_id": "verify", "action_kind": "verify"},
        "destroy": original,
    }
    cleanup = DeclaredCleanup(
        TrialCleanupPlanModel.model_validate(payload),
        native,
        cleanup.store,
        cleanup.clock,
    )

    def unavailable(*args, **kwargs):
        raise OSError("publication unavailable")

    monkeypatch.setattr("aptl.backends.cleanup.retain_cleanup_readback", unavailable)
    with pytest.raises(OSError):
        cleanup.execute("failed")
    assert [action for action, _ in native.calls] == ["verify", "destroy"]
    assert native.state == "absent"
