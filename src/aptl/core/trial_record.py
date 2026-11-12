"""The LilRAE trial record and the seal that closes a trial run for collection.

This record is LilRAE-owned. It is not an RAES experiment-run record: a trial
SDL alone has no admitted RAES plan or task. The seal marker binds the run's
startup manifest digest, as for every sealed run, and its inventory lists every
regular file in the run, including this record.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal, TypeGuard

from pydantic import BaseModel, ConfigDict, Field
import rfc8785
from raes_contracts.contracts import ExperimentEvidenceRecordModel
from raes_contracts.contracts.experiment_capture import (
    ExperimentRawEvidenceContentModel,
)

from aptl.core.archival import DiscoveryIndex, IndexEntry, SealedArtifactSpec
from aptl.core.archival.layout import RUN_MANIFEST_RELPATH, SEAL_MARKER_RELPATH
from aptl.core.archival.seal import (
    SealLimitation,
    SealMarkerInputs,
    build_inventory_entry,
    build_seal_marker,
)
from aptl.core.runstore import LocalRunStore
from aptl.core.evidence.coordinator import AcquisitionResult
from aptl.core.evidence.outcomes import SUCCESS_STATUSES
from aptl.core.experiment.capture_plan import CapturePlan
from aptl.utils.pathsafe import PathContainmentError, open_contained_nofollow

__all__ = [
    "TRIAL_RECORD_RELPATH",
    "TRIAL_RECORD_SCHEMA",
    "TrialParticipantRecord",
    "TrialRecord",
    "seal_trial_record",
    "retain_trial_capture",
]

TRIAL_RECORD_SCHEMA = "lilrae-trial-record/v1"
TRIAL_RECORD_RELPATH = "trial/record.json"
_RUN_VERSION = "1"
_MEDIA_TYPES = {
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".ndjson": "application/x-ndjson",
}
#: Raw captures a trial leaves behind; consumers keep them as opaque blobs.
_CAPTURE_PREFIXES = ("trial/transcripts/", "trial/soc/", "trial/audit/")

TerminalCause = Literal["completed", "deadline", "stopped", "failed"]
ParticipantStatus = Literal["completed", "cancelled", "failed", "not-started"]

# Execution status and evaluator outcome remain separate facts.
_RUN_STATUS = {
    "completed": "completed",
    "deadline": "aborted",
    "stopped": "aborted",
    "failed": "failed",
}


class TrialParticipantRecord(BaseModel):
    """What one participant was asked to do and what it reported."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    address: str
    role: str
    model: str
    context_assets: tuple[str, ...]
    prompt_sha256: str
    status: ParticipantStatus
    started_at: str | None = None
    ended_at: str | None = None
    failure: str | None = None
    output_path: str | None = None
    invocation: dict[str, object] = Field(default_factory=dict)


class TrialRecord(BaseModel):
    """One sealed trial attempt with caller-supplied identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["lilrae-trial-record/v1"] = TRIAL_RECORD_SCHEMA
    run_id: str
    attempt_id: str
    scenario_sha256: str
    deadline: str
    started_at: str
    ended_at: str
    terminal_cause: TerminalCause
    participants: tuple[TrialParticipantRecord, ...]
    #: Each cleanup step and its result, for example ``provider_access: removed``.
    cleanup: dict[str, str] = Field(default_factory=dict)
    capture_plan_id: str | None = Field(
        default=None, pattern=r"^capture-plan-[a-f0-9]{64}$"
    )
    outcome_status: Literal[
        "succeeded", "failed", "partial", "inconclusive", "not-evaluated"
    ] = "not-evaluated"


def retain_trial_capture(
    store: LocalRunStore,
    record: TrialRecord,
    plan: CapturePlan,
    result: AcquisitionResult,
) -> TrialRecord:
    """Retain the admitted demands and their original acquisition reports."""
    if result.scope is None or (
        result.scope.run_id != record.run_id
        or result.scope.attempt_id != record.attempt_id
    ):
        raise ValueError("trial capture belongs to another attempt")
    store.create_run_json_once(
        record.run_id,
        f"evidence/capture-plans/{plan.plan_id}.json",
        json.loads(plan.canonical_bytes),
    )
    store.create_run_json_once(
        record.run_id,
        "trial/capture.json",
        {
            "plan_id": plan.plan_id,
            "run_id": record.run_id,
            "attempt_id": record.attempt_id,
            "reports": [
                {
                    "requirement_id": item.requirement_id,
                    "status": item.status.value,
                    "evidence_record_id": item.evidence_record_id,
                }
                for item in result.reports
            ],
        },
    )
    return record.model_copy(update={"capture_plan_id": plan.plan_id})


def required_data_gaps(run_dir: Path, record: TrialRecord) -> list[str]:
    """Compare the admitted capture demands with retained acquisition outcomes."""
    if record.capture_plan_id is None:
        return ["the trial has no retained capture plan and acquisition reports"]
    try:
        plan = _capture_json(
            run_dir, f"evidence/capture-plans/{record.capture_plan_id}.json"
        )
        capture = _capture_json(run_dir, "trial/capture.json")
        expected = "capture-plan-" + hashlib.sha256(rfc8785.dumps(plan)).hexdigest()
        if record.capture_plan_id != expected or (
            capture["plan_id"],
            capture["run_id"],
            capture["attempt_id"],
        ) != (expected, record.run_id, record.attempt_id):
            raise ValueError("capture identity differs")
        demands = {item["demand"]["demand_id"] for item in plan["bindings"]}
        if not demands or len(demands) != len(plan["bindings"]):
            raise ValueError("capture requirements are empty or ambiguous")
        reports = {item["requirement_id"]: item for item in capture["reports"]}
        if len(reports) != len(capture["reports"]) or set(reports) != demands:
            raise ValueError("capture requirement set differs")
        success = {status.value for status in SUCCESS_STATUSES}
        return [
            f"required capture {name} was not retained successfully"
            for name, item in sorted(reports.items())
            if item["status"] not in success
            or not _capture_record_present(
                run_dir, record, name, item["evidence_record_id"]
            )
        ]
    except OSError, ValueError, KeyError, TypeError, PathContainmentError:
        return [
            "the trial capture plan or acquisition reports are unavailable or inconsistent"
        ]


def _capture_json(run_dir: Path, path: str) -> dict[str, Any]:
    """Read one bounded capture carrier without following links."""
    with open_contained_nofollow(run_dir, path) as source:
        data = source.read(4 * 1024 * 1024 + 1)
    if len(data) > 4 * 1024 * 1024:
        raise ValueError("capture carrier exceeds the bound")
    return json.loads(data)


def _capture_record_present(
    run_dir: Path, trial: TrialRecord, requirement: str, record_id: object
) -> bool:
    """Verify the acquisition record's identity and original content checksum."""
    if not _is_record_name(record_id):
        return False
    try:
        evidence = ExperimentEvidenceRecordModel.model_validate(
            _capture_json(run_dir, f"evidence/records/{record_id}.json")
        )
        return _evidence_identity_matches(
            evidence, trial, requirement, record_id
        ) and _content_checksum_matches(run_dir, evidence.raw_content)
    except OSError, ValueError, TypeError, PathContainmentError:
        return False


def _is_record_name(record_id: object) -> TypeGuard[str]:
    """Accept only a non-empty record identifier that is one plain file name."""
    return (
        isinstance(record_id, str)
        and bool(record_id)
        and Path(record_id).name == record_id
    )


def _evidence_identity_matches(
    evidence: ExperimentEvidenceRecordModel,
    trial: TrialRecord,
    requirement: str,
    record_id: str,
) -> bool:
    """Match the record to this run, capture plan, requirement and attempt."""
    return (
        evidence.evidence_record_id == record_id
        and evidence.run_ref.ref_id == trial.run_id
        and evidence.capture_spec_ref.ref_id == trial.capture_plan_id
        and evidence.capture_requirement_ref == requirement
        and any(
            ref.ref_id == f"attempt:{trial.attempt_id}" for ref in evidence.source_refs
        )
    )


def _content_checksum_matches(
    run_dir: Path, content: ExperimentRawEvidenceContentModel
) -> bool:
    """Compare the retained content with its recorded SHA-256 checksum."""
    checksum = content.content_checksum
    if (
        content.content_uri is None
        or checksum is None
        or checksum.algorithm != "sha256"
    ):
        return False
    with open_contained_nofollow(run_dir, content.content_uri) as source:
        return hashlib.file_digest(source, "sha256").hexdigest() == checksum.value


def seal_trial_record(
    store: LocalRunStore, record: TrialRecord, *, gaps: tuple[str, ...] = ()
) -> Path:
    """Write the record once and seal every regular file in the run.

    Call it only after every evidence producer and credential cleanup ended.
    ``gaps`` names trial data that the caller could not produce; the seal also
    checks the data a complete trial must leave, and lists each gap.
    """
    run_id = record.run_id
    store.create_run_json_once(
        run_id, TRIAL_RECORD_RELPATH, record.model_dump(mode="json")
    )
    run_dir = store.get_run_path(run_id)
    manifest = run_dir / RUN_MANIFEST_RELPATH
    if not manifest.is_file() or manifest.is_symlink():
        raise RuntimeError("the trial run has no startup manifest to seal")
    digest = "sha256:" + hashlib.sha256(manifest.read_bytes()).hexdigest()
    with store.finalization_lock(run_id):
        inventory = [
            build_inventory_entry(store, run_id, spec) for spec in _run_files(run_dir)
        ]
        limitations = (
            []
            if record.terminal_cause == "completed"
            else [
                SealLimitation(
                    "partial-trial",
                    f"The trial ended by {record.terminal_cause}; participant evidence is partial.",
                )
            ]
        )
        limitations += [
            SealLimitation("required-data-missing", gap)
            for gap in (*gaps, *required_data_gaps(run_dir, record))
        ]
        marker = build_seal_marker(
            SealMarkerInputs(
                run_id=run_id,
                run_version=_RUN_VERSION,
                run_status=_RUN_STATUS[record.terminal_cause],
                outcome_status=record.outcome_status,
                run_record_digest=digest,
                inventory=inventory,
                contract_versions=[TRIAL_RECORD_SCHEMA],
                limitations=limitations,
                completeness_statement=(
                    "The inventory lists every regular file in the trial run at its seal."
                ),
            )
        )
        entry = IndexEntry(
            run_id=run_id,
            run_version=_RUN_VERSION,
            manifest_digest=digest,
            seal_state="sealed",
            terminal_at=record.ended_at,
            location=RUN_MANIFEST_RELPATH,
        )
        index = DiscoveryIndex(store.base_dir)
        index.prepare(entry)
        path = store.commit_seal_marker(run_id, marker)
        index.commit(entry)
    return path


def _run_files(run_dir: Path) -> list[SealedArtifactSpec]:
    """List regular files below the run directory without following links."""
    specs = []
    for root, directories, files in os.walk(run_dir, followlinks=False):
        directories[:] = sorted(
            name for name in directories if not (Path(root) / name).is_symlink()
        )
        for name in sorted(files):
            path = Path(root) / name
            relative = path.relative_to(run_dir).as_posix()
            if (
                path.is_symlink()
                or not path.is_file()
                or relative == SEAL_MARKER_RELPATH
            ):
                continue
            role = (
                "trial-record"
                if relative == TRIAL_RECORD_RELPATH
                else "evidence-record"
            )
            if relative == RUN_MANIFEST_RELPATH:
                role = "manifest"
            elif relative.startswith(_CAPTURE_PREFIXES):
                role = "evidence-blob"
            specs.append(
                SealedArtifactSpec(
                    path=relative,
                    media_type=_MEDIA_TYPES.get(
                        path.suffix, "application/octet-stream"
                    ),
                    role=role,
                )
            )
    return specs
