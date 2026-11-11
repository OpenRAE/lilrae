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
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aptl.core.archival import DiscoveryIndex, IndexEntry, SealedArtifactSpec
from aptl.core.archival.layout import RUN_MANIFEST_RELPATH, SEAL_MARKER_RELPATH
from aptl.core.archival.seal import (
    SealLimitation,
    SealMarkerInputs,
    build_inventory_entry,
    build_seal_marker,
)
from aptl.core.runstore import LocalRunStore

__all__ = [
    "TRIAL_RECORD_RELPATH",
    "TRIAL_RECORD_SCHEMA",
    "TrialParticipantRecord",
    "TrialRecord",
    "seal_trial_record",
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

# The seal records the real terminal state; LilRAE does not evaluate outcomes.
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


def required_data_gaps(run_dir: Path, record: TrialRecord) -> list[str]:
    """Name each piece of trial data that a complete trial must leave in its run.

    Every participant ends normally and leaves its raw chat; the host audit log
    and each trial-end capture source report ``captured``.
    """
    gaps = [
        f"participant {item.address} ended {item.status}"
        for item in record.participants
        if item.status != "completed"
    ]
    gaps += [
        f"raw chat of {item.address} is missing"
        for item in record.participants
        if not (run_dir / f"trial/transcripts/{item.address}.json").is_file()
    ]
    if _captured_status(run_dir / "trial/audit/status.json") != "captured":
        gaps.append("the host audit log was not captured")
    soc = run_dir / "trial/soc/manifest.json"
    if soc.is_file():
        sources = json.loads(soc.read_text(encoding="utf-8"))
        gaps += [
            f"trial-end source {name} was not captured"
            for name, item in sorted(sources.items())
            if item.get("status") != "captured"
        ]
    return gaps


def _captured_status(path: Path) -> object:
    """Return a capture status file's ``status``; an absent file has none."""
    return (
        json.loads(path.read_text(encoding="utf-8")).get("status")
        if path.is_file()
        else None
    )


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
                outcome_status="not-evaluated",
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
