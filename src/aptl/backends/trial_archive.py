"""Seal one producer-owned recovery record and its original artifact snapshot."""

import hashlib
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Literal

import rfc8785
from pydantic import BaseModel, ConfigDict
from raes_contracts.artifact_checksums import checksum_hasher
from raes_contracts.assigned_trial import TrialAssignmentModel, TrialOutcomeModel
from raes_contracts.canonical import canonical_contract_digest
from raes_contracts.contracts import (
    ExperimentChecksumModel,
    ExperimentEvidenceRecordModel,
    ExperimentRunModel,
    validate_admitted_trial_run,
)
from raes_contracts.contracts.base import Rfc3339DateTimeString
from raes_contracts.errors import RaesError
from raes_contracts.json_ingress import parse_bounded_json_object
from raes_contracts.runtime_state import RuntimeSnapshotEnvelope
from raes_runtime.experiment_records import ExperimentRecordSource
from raes_runtime.snapshot_contract import runtime_snapshot_contract_model

from aptl.core.archival.coordinator import SealResult, seal_produced_run
from aptl.core.archival.seal import SealLimitation, SealedArtifactSpec
from aptl.core.archival.snapshot import (
    SnapshotArtifact,
    SnapshotLimits,
    snapshot_run_files,
)
from aptl.core.archival.verify import verify_sealed_archive
from aptl.core.correlation.clock import ClockProvider
from aptl.core.runstore import LocalRunStore, RunStoreConflictError
from aptl.utils.pathsafe import (
    PathContainmentError,
    REASON_NOT_FOUND,
    create_exclusive_nofollow,
    open_contained_nofollow,
    open_private_dir_contained_nofollow,
    read_contained_nofollow,
)

_OBSERVATION = "archive/observation.json"


@dataclass(frozen=True)
class ArchiveOptions:
    """Installed bounds, producer validation and local seal limitations."""

    validation_passed: bool = False
    limitations: tuple[SealLimitation, ...] = ()
    limits: SnapshotLimits = SnapshotLimits()


class ArchiveObservation(BaseModel):
    """Stable local routing facts; the record retains its own event times."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: Literal["lilrae.recovery-archive/v1"] = "lilrae.recovery-archive/v1"
    run_id: str
    run_version: str
    snapshot_digest: str
    observed_at: Rfc3339DateTimeString


def _validate_binding(
    run: ExperimentRunModel,
    source: ExperimentRecordSource,
    outcome: TrialOutcomeModel,
    assignment: TrialAssignmentModel,
) -> None:
    """Check exact admission, run and retained phase identity joins."""
    accounting = run.execution_accounting
    if accounting is None or not source.attempts:
        raise ValueError("trial-archive-identity-mismatch")
    actual = (
        run.run_id,
        accounting.plan_entry_id,
        accounting.attempts[-1].execution_attempt_id,
    )
    expected = (
        source.run_id,
        assignment.plan_entry_id,
        assignment.execution_attempt_id,
    )
    if (
        actual != expected
        or run.run_id != assignment.plan.entries[assignment.plan_entry_id].run_id
        or outcome.assignment_digest != assignment.content_digest
        or source.plan.model_dump(mode="json")
        != assignment.plan.model_dump(mode="json")
        or source.attempts[-1].execution_attempt_id != assignment.execution_attempt_id
    ):
        raise ValueError("trial-archive-identity-mismatch")
    validate_admitted_trial_run(
        source.plan,
        run,
        [
            attempt.cleanup_receipt
            for attempt in accounting.attempts
            if attempt.cleanup_receipt is not None
        ],
    )


def _retain_model(store: LocalRunStore, run_id: str, model: BaseModel) -> None:
    """Persist one public commitment under its canonical content digest."""
    payload = model.model_dump(mode="json")
    digest = hashlib.sha256(rfc8785.dumps(payload)).hexdigest()
    store.create_run_json_once(run_id, f"runtime/recovery-facts/{digest}.json", payload)


def _retain_source(
    store: LocalRunStore,
    source: ExperimentRecordSource,
    assignment: TrialAssignmentModel,
    outcome: TrialOutcomeModel,
) -> None:
    """Keep public sources and safe snapshots beside original evidence."""
    models = (
        assignment,
        outcome,
        source.plan,
        source.instantiated_scenario,
        *source.processor_plans,
    )
    # Private runtime decisions can contain credential-bearing internal state.
    # The public assignment/outcome carriers retain portable facts and times;
    # the original control journal stays with its RAES owner.
    for model in models:
        _retain_model(store, source.run_id, model)
    for snapshot in source.execution_snapshots.values():
        _retain_model(
            store,
            source.run_id,
            runtime_snapshot_contract_model(
                RuntimeSnapshotEnvelope(snapshot=snapshot), include_trial_history=True
            ),
        )


def _archive_store(store: LocalRunStore, digest: str) -> LocalRunStore:
    """Open a private no-follow destination for one immutable snapshot."""
    relative = Path("archives") / digest
    fd = open_private_dir_contained_nofollow(store.base_dir, relative)
    try:
        return LocalRunStore(store.base_dir / relative)
    finally:
        os.close(fd)


def _verify_bytes(
    uri: str,
    checksum: ExperimentChecksumModel,
    files: dict[str, SnapshotArtifact],
    size: int | None = None,
) -> None:
    """Match retained bytes to the original declared size and digest."""
    artifact = files.get(uri)
    if artifact is None or (size is not None and len(artifact.data) != size):
        raise ValueError("trial-archive-content-unavailable")
    hasher = checksum_hasher(checksum.algorithm)
    hasher.update(artifact.data)
    if hasher.hexdigest() != checksum.value.lower():
        raise ValueError("trial-archive-content-mismatch")


def _verify_record(
    record: ExperimentEvidenceRecordModel, files: dict[str, SnapshotArtifact]
) -> None:
    """Verify each declared local content reference in one evidence record."""
    raw = record.raw_content
    if raw.content_uri is not None:
        if raw.content_checksum is None:
            raise ValueError("trial-archive-checksum-unavailable")
        _verify_bytes(raw.content_uri, raw.content_checksum, files)
    if raw.artifact_ref is not None:
        artifact = raw.artifact_ref
        _verify_bytes(artifact.uri, artifact.checksum, files, artifact.size_bytes)


def _verify_retained_record(
    record: ExperimentEvidenceRecordModel,
    run_id: str,
    seen: dict[tuple[str, str], str],
    files: dict[str, SnapshotArtifact],
) -> None:
    """Reject cross-run evidence and conflicting versions before byte verification."""
    if record.run_ref.ref_kind != "run" or record.run_ref.ref_id != run_id:
        raise ValueError("trial-archive-evidence-identity-mismatch")
    key = record.evidence_record_id, record.record_version
    digest = canonical_contract_digest(record)
    if key in seen and seen[key] != digest:
        raise ValueError("trial-archive-evidence-conflict")
    if key not in seen:
        _verify_record(record, files)
        seen[key] = digest


def _verify_evidence(
    run: ExperimentRunModel,
    source: ExperimentRecordSource,
    outcome: TrialOutcomeModel,
    artifacts: tuple[SnapshotArtifact, ...],
) -> None:
    """Join original evidence across the producer and retained phase facts."""
    files = {artifact.path: artifact for artifact in artifacts}
    groups = [item.observation.evidence for item in source.observations]
    groups.extend(fact.observation.evidence for fact in outcome.facts)
    if run.execution_accounting is not None:
        groups.extend(
            attempt.evidence_records for attempt in run.execution_accounting.attempts
        )
    seen: dict[tuple[str, str], str] = {}
    for records in groups:
        for record in records:
            _verify_retained_record(record, run.run_id, seen, files)
    for artifact in run.evidence_artifacts:
        _verify_bytes(artifact.uri, artifact.checksum, files, artifact.size_bytes)


def _publish_artifacts(
    store: LocalRunStore, run_id: str, artifacts: tuple[SnapshotArtifact, ...]
) -> None:
    """Copy a closed inventory create-once and refuse conflicting bytes."""
    for artifact in artifacts:
        path = f"{run_id}/{artifact.path}"
        try:
            create_exclusive_nofollow(store.base_dir, path, artifact.data)
        except FileExistsError:
            if read_contained_nofollow(store.base_dir, path) != artifact.data:
                raise RunStoreConflictError("trial-archive-artifact-conflict") from None


def _observation(
    store: LocalRunStore, run: ExperimentRunModel, digest: str, clock: ClockProvider
) -> ArchiveObservation:
    """Retain one bounded observation time for idempotent publication."""
    try:
        with open_contained_nofollow(
            store.base_dir, f"{run.run_id}/{_OBSERVATION}"
        ) as source:
            data = source.read(16385)
    except PathContainmentError as failure:
        if failure.reason != REASON_NOT_FOUND:
            raise
        retained = ArchiveObservation(
            run_id=run.run_id,
            run_version=run.run_version,
            snapshot_digest=digest,
            observed_at=clock.now(),
        ).model_dump(mode="json")
        store.create_run_json_once(run.run_id, _OBSERVATION, retained)
        data = rfc8785.dumps(retained)
    observed = ArchiveObservation.model_validate(
        parse_bounded_json_object(data, max_bytes=16384, max_depth=8)
    )
    if (observed.run_id, observed.run_version, observed.snapshot_digest) != (
        run.run_id,
        run.run_version,
        digest,
    ):
        raise ValueError("trial-archive-observation-conflict")
    return observed


def seal_recovered_run(
    run: ExperimentRunModel,
    *,
    source: ExperimentRecordSource,
    outcome: TrialOutcomeModel,
    assignment: TrialAssignmentModel,
    store: LocalRunStore,
    clock: ClockProvider,
    options: ArchiveOptions = ArchiveOptions(),
) -> SealResult:
    """Freeze original facts and bytes without sealing the live evidence store."""
    try:
        assignment = TrialAssignmentModel.reconstruct(assignment)
        outcome = TrialOutcomeModel.reconstruct(outcome)
        run = ExperimentRunModel.model_validate(run.model_dump(mode="json"))
        _validate_binding(run, source, outcome, assignment)
        with store.finalization_lock(run.run_id):
            _retain_source(store, source, assignment, outcome)
            artifacts = snapshot_run_files(store, run.run_id, limits=options.limits)
        _verify_evidence(run, source, outcome, artifacts)
        if any(
            item.path in {"manifest.json", "seal.json", _OBSERVATION}
            for item in artifacts
        ):
            raise ValueError("trial-archive-source-reserved")
        specifications = tuple(item.specification() for item in artifacts)
        accepted = (
            options.limitations
            if options.validation_passed
            else (
                *options.limitations,
                SealLimitation(
                    "task-evidence-unverified", "RAES did not verify all task evidence."
                ),
            )
        )
        digest = hashlib.sha256(
            rfc8785.dumps(
                {
                    "record": canonical_contract_digest(run),
                    "assignment": assignment.content_digest,
                    "outcome": outcome.content_digest,
                    "validation_passed": options.validation_passed,
                    "limitations": [item.projection() for item in accepted],
                    "artifacts": [
                        [item.path, item.expected_sha256, item.expected_size_bytes]
                        for item in specifications
                    ],
                }
            )
        ).hexdigest()
        archive = _archive_store(store, digest)
        with archive.finalization_lock(run.run_id):
            prior = verify_sealed_archive(archive.base_dir, run.run_id)
            if prior is None:
                archive.create_run(run.run_id)
                _publish_artifacts(archive, run.run_id, artifacts)
            observed = _observation(archive, run, digest, clock)
            return seal_produced_run(
                run,
                store=archive,
                artifacts=(
                    *specifications,
                    SealedArtifactSpec(
                        _OBSERVATION, "application/json", "archive-observation"
                    ),
                ),
                limitations=accepted,
                observed_at=observed.observed_at,
            )
    except ValueError, OSError, PathContainmentError, RaesError:
        raise ValueError("trial-archive-unavailable") from None
