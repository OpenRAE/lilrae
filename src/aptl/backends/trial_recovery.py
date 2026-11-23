"""Reconcile and archive one interrupted assigned trial through its RAES owner."""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import rfc8785
from pydantic import BaseModel, ConfigDict
from raes_contracts.assigned_trial import TrialAssignmentControlModel, TrialOutcomeModel
from raes_contracts.canonical import canonical_contract_digest
from raes_contracts.contracts import ExperimentRunModel
from raes_contracts.contracts.trial_replacement_archive import (
    replacement_resources_reusable,
)
from raes_contracts.json_ingress import parse_bounded_json_object
from raes_contracts.trial_unit import TrialUnitResult
from raes_runtime import RuntimeControlPlane
from raes_runtime.errors import TrialPending
from raes_runtime.runtime_assigned_trial import AssignedTrial

from aptl.backends.trial_archive import ArchiveOptions, seal_recovered_run
from aptl.backends.trial_serving import LilraeTrialUnit, OwnedTrial
from aptl.core.archival.coordinator import SealResult
from aptl.core.archival.seal import SealLimitation
from aptl.core.archival.verify import VerifiedArchive, verify_sealed_archive
from aptl.core.correlation.clock import ClockProvider
from aptl.core.lifecycle_errors import LifecycleBusyError
from aptl.core.trial_intent import (
    ContractDigest,
    Digest,
    TrialIntent,
    load_trial_intent,
    trial_intent,
)
from aptl.core.trial_ownership import TRIAL_FENCE, trial_fence_owner
from aptl.utils.pathsafe import (
    REASON_NOT_FOUND,
    PathContainmentError,
    open_contained_nofollow,
    remove_contained_nofollow,
)


@dataclass(frozen=True)
class TrialRecoveryResult:
    """Original owner facts, a verified immutable archive and reuse disposition."""

    outcome: TrialOutcomeModel
    run: ExperimentRunModel
    archive: VerifiedArchive
    manifest_path: Path
    resources_reusable: bool
    idempotent: bool


class RecoveryReceipt(BaseModel):
    """Local archive routing after cleanup; never an execution authorization."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )
    schema_version: Literal["lilrae.trial-recovery/v1"] = "lilrae.trial-recovery/v1"
    intent: TrialIntent
    assignment_digest: ContractDigest
    outcome_digest: ContractDigest
    archive_digest: Digest
    run_record_digest: ContractDigest


def _receipt_name(binding: AssignedTrial, outcome: TrialOutcomeModel) -> str:
    """Route replay by the exact assignment and original outcome digest."""
    return hashlib.sha256(
        rfc8785.dumps(
            [
                binding.assignment_digest,
                outcome.content_digest,
            ]
        )
    ).hexdigest()


def _intent(unit: LilraeTrialUnit, owned: OwnedTrial) -> TrialIntent:
    """Reconstruct expected commitments from the installed native owners."""
    return trial_intent(
        owned.request, unit.cleanup.native.binding, owned.owner, owned.daemon
    )


def _load_receipt(
    unit: LilraeTrialUnit,
    binding: AssignedTrial,
    outcome: TrialOutcomeModel,
) -> RecoveryReceipt | None:
    """Read one bounded no-follow receipt without inventing absent state."""
    store = unit.cleanup.store
    try:
        with open_contained_nofollow(
            store.base_dir, f"trial-recovery/{_receipt_name(binding, outcome)}.json"
        ) as source:
            data = source.read(16385)
    except PathContainmentError as failure:
        if failure.reason == REASON_NOT_FOUND:
            return None
        raise
    return RecoveryReceipt.model_validate(
        parse_bounded_json_object(data, max_bytes=16384, max_depth=8)
    )


def _completed_replay(
    unit: LilraeTrialUnit,
    binding: AssignedTrial,
    outcome: TrialOutcomeModel,
) -> TrialRecoveryResult | None:
    """Verify historical recovery without changing a later delivery."""
    store = unit.cleanup.store
    receipt = _load_receipt(unit, binding, outcome)
    if receipt is None:
        return None
    owned = unit.describe_trial(binding.request)
    intent = load_trial_intent(store, _intent(unit, owned))
    if (
        receipt.intent,
        receipt.assignment_digest,
        receipt.outcome_digest,
    ) != (
        intent,
        binding.assignment_digest,
        outcome.content_digest,
    ):
        raise ValueError("trial-recovery-receipt-conflict")
    # A crash between receipt publication and fence removal still needs the
    # normal locked path. A later owner's fences must never be changed here.
    fences = (trial_fence_owner(owned.project), trial_fence_owner(owned.daemon_root))
    if owned.owner in fences:
        return None
    archive_root = store.base_dir / "archives" / receipt.archive_digest
    verified = verify_sealed_archive(archive_root, owned.request.run_id)
    if verified is None or verified.run_record_digest != receipt.run_record_digest:
        raise ValueError("trial-recovery-archive-unavailable")
    manifest = archive_root / owned.request.run_id / "manifest.json"
    with open_contained_nofollow(
        archive_root, f"{owned.request.run_id}/manifest.json"
    ) as source:
        run = ExperimentRunModel.model_validate_json(source.read(16 * 1024 * 1024 + 1))
    if canonical_contract_digest(run) != receipt.run_record_digest:
        raise ValueError("trial-recovery-record-conflict")
    if all(fence is None for fence in fences) and owned.readiness.references:
        # Finish an interrupted in-process handoff after both fence removals.
        # A fresh gate has no retained probe authority and must stay unbound.
        owned.readiness.complete_retained_delivery(
            owned.request,
            project=owned.project,
            daemon_root=owned.daemon_root,
            owner=owned.owner,
        )
    return TrialRecoveryResult(outcome, run, verified, manifest, True, True)


def _seal_outcome(
    unit: LilraeTrialUnit,
    binding: AssignedTrial,
    outcome: TrialOutcomeModel,
    result: TrialUnitResult | None,
    clock: ClockProvider,
    *,
    probe_cessation_proven: bool,
) -> SealResult:
    """Ingest original facts and seal the matching shared-producer record."""
    unit.reporting.runtime.ingest_trial_outcome(
        unit.reporting.experiment_id, outcome, identity=unit.reporting.identity
    )
    bundle = unit.reporting.report(binding.request, result)
    run = next(run for run in bundle.runs if run.run_id == binding.request.run_id)
    source = next(source for source in bundle.sources if source.run_id == run.run_id)
    return seal_recovered_run(
        run,
        source=source,
        assignment=binding.assignment,
        outcome=outcome,
        store=unit.cleanup.store,
        clock=clock,
        options=ArchiveOptions(
            validation_passed=bundle.validation_by_run.get(run.run_id) == "passed",
            limitations=()
            if probe_cessation_proven
            else (
                SealLimitation(
                    "probe-cessation-unverified",
                    "Original readiness probe cessation is unverified; target reuse remains blocked.",
                ),
            ),
        ),
    )


def _reusable(
    unit: LilraeTrialUnit, owned: OwnedTrial, outcome: TrialOutcomeModel
) -> bool:
    """Require native cleanup verification and complete probe cessation."""
    cleanup = next(
        (
            fact.observation
            for fact in outcome.facts
            if fact.observation.kind == "cleanup"
        ),
        None,
    )
    if cleanup is None:
        return False
    unit.cleanup.verify_observation(cleanup)
    return (
        replacement_resources_reusable(owned.request.cleanup_plan, cleanup.receipt)
        and bool(owned.readiness.references)
        and not owned.readiness.has_pending_probes
    )


def recover_interrupted_trial(
    unit: LilraeTrialUnit,
    binding: AssignedTrial,
    control: TrialAssignmentControlModel,
    *,
    runtime: RuntimeControlPlane,
    clock: ClockProvider,
    identity: object,
) -> TrialRecoveryResult:
    """Stop the exact admitted assignment; never choose another plan entry.

    The coordinator supplies cancellation. RAES retains phase decisions and
    determines cessation and cleanup. Unknown work keeps both placement fences.
    """
    try:
        control = TrialAssignmentControlModel.reconstruct(control)
        if (
            control.assignment_digest != binding.assignment_digest
            or not control.cancelled
            or control.prepare_retry
        ):
            raise ValueError
    except ValueError:
        raise ValueError("trial-recovery-control-invalid") from None
    try:
        return _recover_owned_trial(unit, binding, control, runtime, clock, identity)
    except LifecycleBusyError:
        raise ValueError("trial-recovery-busy") from None
    except Exception:
        # Installed owners and malformed retained input must not expose their
        # raw exception messages, credentials or parser payloads to the caller.
        # Process cancellation still propagates and retains the ownership fences.
        raise ValueError("trial-recovery-unavailable") from None


def _recover_owned_trial(
    unit: LilraeTrialUnit,
    binding: AssignedTrial,
    control: TrialAssignmentControlModel,
    runtime: RuntimeControlPlane,
    clock: ClockProvider,
    identity: object,
) -> TrialRecoveryResult:
    """Reconcile the original ledger under its placement ownership."""
    if unit.runtime_unit is not binding:
        raise ValueError("trial-recovery-binding-mismatch")
    outcome = binding.outcome(identity=identity)
    unit.admit(binding.request)
    replay = _completed_replay(unit, binding, outcome)
    if replay is not None:
        return replay
    with unit.owned_trial(binding.request, recovery=True) as owned:
        binding.advance(identity=identity, control=control)
        try:
            result = binding.execute_trial(owned.request, identity=identity)
        except TrialPending:
            result = None
        outcome = binding.outcome(identity=identity)
        reusable = _reusable(unit, owned, outcome)
        if reusable and unit.participants is not None:
            unit.participants.finish(owned.request)
        sealed = _seal_outcome(
            unit,
            binding,
            outcome,
            result,
            clock,
            probe_cessation_proven=bool(owned.readiness.references)
            and not owned.readiness.has_pending_probes,
        )
        verified = verify_sealed_archive(
            sealed.manifest_path.parents[1], owned.request.run_id
        )
        if verified is None:
            raise ValueError("trial-recovery-archive-unavailable")
        if owned.readiness.observe_placement(unit.placement.daemon_id) != owned.daemon:
            raise ValueError("trial-daemon-changed")
        if reusable:
            # This retires only the already selected worker run. A failure keeps
            # native exclusion; no local scheduler or retry decision is created.
            runtime.retire_run("run:" + owned.request.run_id)
            receipt = RecoveryReceipt(
                intent=_intent(unit, owned),
                assignment_digest=binding.assignment_digest,
                outcome_digest=outcome.content_digest,
                archive_digest=sealed.manifest_path.parents[1].name,
                run_record_digest=sealed.run_record_digest,
            )
            unit.cleanup.store.create_json_once(
                "trial-recovery",
                _receipt_name(binding, outcome),
                receipt.model_dump(mode="json"),
            )
            remove_contained_nofollow(owned.project, TRIAL_FENCE)
            remove_contained_nofollow(owned.daemon_root, TRIAL_FENCE)
            owned.readiness.complete_delivery(owned.request)
        return TrialRecoveryResult(
            outcome,
            sealed.run,
            verified,
            sealed.manifest_path,
            reusable,
            sealed.idempotent,
        )
