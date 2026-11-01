"""Retain cleanup readback through the existing evidence and run-store owners."""

from dataclasses import asdict
import hashlib

import rfc8785
from raes_contracts.contracts import (
    ExperimentEvidenceRecordModel,
    TrialCleanupReceiptModel,
)

from aptl.core.cleanup import CleanupBinding, CleanupReadback
from aptl.core.correlation.clock import ClockProvider
from aptl.core.evidence.content_store import create_content_addressed
from aptl.core.evidence.protocol import CollectorOutcome
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.evidence.records import RecordDisclosure, build_evidence_record
from aptl.core.experiment.capture_registry import (
    CaptureBinding,
    CaptureLimits,
    CaptureVisibility,
)
from aptl.core.lifecycle_guard import lifecycle_recovery_command
from aptl.core.runstore import LocalRunStore
from aptl.utils.pathsafe import open_contained_nofollow

_MAX_BYTES = 128 * 1024


def _read(store: LocalRunStore, run_id: str, path: str) -> bytes:
    with open_contained_nofollow(store.get_run_path(run_id), path) as handle:
        data = handle.read(_MAX_BYTES + 1)
    if len(data) > _MAX_BYTES:
        raise ValueError("cleanup evidence exceeds its byte bound")
    return data


def load_cleanup_receipt(
    store: LocalRunStore, run_id: str, receipt_id: str
) -> TrialCleanupReceiptModel:
    """Read the exact retained receipt through the bounded no-follow boundary."""
    return TrialCleanupReceiptModel.model_validate_json(
        _read(store, run_id, f"cleanup/receipts/{receipt_id}.json")
    )


def retain_cleanup_readback(
    store: LocalRunStore,
    clock: ClockProvider,
    scope: CleanupBinding,
    obligation_id: str,
    readback: CleanupReadback,
) -> ExperimentEvidenceRecordModel:
    """Publish original safe facts and a canonical RAES evidence record."""
    payload = {
        "plan_entry_id": scope.plan_entry_id,
        "run_id": scope.run_id,
        "execution_attempt_id": scope.execution_attempt_id,
        "native_attempt_id": scope.native_attempt_id,
        "boundary_id": scope.boundary_id,
        "obligation_id": obligation_id,
        "readback": asdict(readback),
        "observed_at": clock.now(),
        "recovery_command": lifecycle_recovery_command(
            "lilrae lab stop -v --yes", scope.project_dir
        ),
    }
    data = rfc8785.dumps(payload)
    if len(data) > _MAX_BYTES:
        raise BufferError("cleanup evidence exceeds its byte bound")
    content = create_content_addressed(
        store,
        scope.run_id,
        (data,),
        subdir="cleanup/content",
        max_bytes=_MAX_BYTES,
    )
    binding = CaptureBinding(
        capture_spec_id="lilrae.native-cleanup",
        requirement_id=obligation_id,
        window_refs=(scope.execution_attempt_id,),
        registration_id="native-cleanup",
        implementation_version="1",
        contract_version="1",
        effective_config_digest=content.digest,
        channel_ref_id="native-cleanup",
        channel_ref_version="1",
        channel_kind="backend-native",
        capture_kind="observation",
        capture_scope="backend",
        expected_media_types=("application/json",),
        required_artifact_roles=(),
        sensitivity="restricted",
        redaction_required=False,
        integrity_requirements=("sha256",),
        retention_policy=None,
        loss_disclosure_required=True,
        visibility_class=CaptureVisibility.APPARATUS_ONLY,
        limits=CaptureLimits(_MAX_BYTES, 1, 1),
    )
    record = build_evidence_record(
        binding=binding,
        run_id=scope.run_id,
        planned_trial_id=scope.plan_entry_id,
        content=content,
        outcome=CollectorOutcome(
            status=CollectorStatus.OK,
            started_at=clock.now(),
            finished_at=clock.now(),
            event_count=len(readback.resources),
        ),
        captured_at=clock.now(),
        disclosure=RecordDisclosure(sensitivity="restricted", redaction_state="none"),
    )
    store.create_run_json_once(
        scope.run_id,
        f"cleanup/records/{record.evidence_record_id}.json",
        record.model_dump(mode="json"),
    )
    return record


def verify_cleanup_record(
    store: LocalRunStore, record: ExperimentEvidenceRecordModel
) -> None:
    """Resolve the record and exact native bytes, rather than trust references."""
    run_id = record.run_ref.ref_id
    stored = _read(store, run_id, f"cleanup/records/{record.evidence_record_id}.json")
    if ExperimentEvidenceRecordModel.model_validate_json(stored) != record:
        raise ValueError("cleanup evidence record changed")
    content = record.raw_content
    if content.content_uri is None or content.content_checksum is None:
        raise ValueError("cleanup evidence content is missing")
    data = _read(store, run_id, content.content_uri)
    if (
        len(data) > _MAX_BYTES
        or hashlib.sha256(data).hexdigest() != content.content_checksum.value
    ):
        raise ValueError("cleanup evidence bytes changed")
