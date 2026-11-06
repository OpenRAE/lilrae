"""The LilRAE trial record and the seal that closes a trial run for collection.

This record is LilRAE-owned. It is not an RAES experiment-run record: a trial
SDL alone has no admitted RAES plan or task.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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

TerminalCause = Literal["completed", "deadline", "stopped", "failed"]
ParticipantStatus = Literal["completed", "cancelled", "failed", "not-started"]


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


def seal_trial_record(store: LocalRunStore, record: TrialRecord) -> Path:
    """Write the record once and seal every regular file in the run."""
    raise RuntimeError("trial sealing is not supported")
