"""The caller-supplied identity and deadline of one trial attempt."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = ["TrialAttempt", "TrialUnit", "load_trial_unit", "parse_trial_attempt"]

#: The canonical instantiated snapshot limit that family trial admission applies.
MAX_TRIAL_UNIT_BYTES = 32 * 1024 * 1024

# The run store's identifier contract: a run ID names one run directory.
_IDENTIFIER = re.compile(r"^\w[\w.-]{0,127}$", re.ASCII)
_UTC_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")


@dataclass(frozen=True)
class TrialUnit:
    """One admitted RAES plan entry and its exact instantiated snapshot bytes."""

    plan: Any = field(repr=False)
    plan_entry_id: str
    snapshot: bytes = field(repr=False)


@dataclass(frozen=True)
class TrialAttempt:
    """Run and attempt IDs and the UTC deadline that the caller owns.

    ``unit`` is the admitted plan entry to run. Without it, the trial runs the
    SDL that the project selects.
    """

    run_id: str
    attempt_id: str
    deadline: datetime
    unit: TrialUnit | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        for name, value in (("run ID", self.run_id), ("attempt ID", self.attempt_id)):
            if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value) or ".." in value:
                raise ValueError(f"trial {name} is invalid")
        if self.deadline.tzinfo is None or self.deadline.utcoffset() != UTC.utcoffset(None):
            raise ValueError("trial deadline must be a UTC time")


def parse_trial_attempt(
    run_id: str | None, attempt_id: str | None, deadline: str | None
) -> TrialAttempt | None:
    """Return ``None`` with no trial options, or one validated attempt.

    Raise ``ValueError`` for a partial option set, an unsafe ID, or a deadline
    that is not an RFC 3339 UTC time.
    """
    values = (run_id, attempt_id, deadline)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError("--run-id, --attempt-id and --deadline are required together")
    assert deadline is not None
    if not _UTC_TIME.fullmatch(deadline):
        raise ValueError("--deadline must be an RFC 3339 UTC time ending in Z")
    parsed = datetime.fromisoformat(deadline.replace("Z", "+00:00")).astimezone(UTC)
    return TrialAttempt(str(run_id), str(attempt_id), parsed)


def load_trial_unit(path: Path) -> TrialUnit:
    """Read one ``{plan, plan_entry_id, snapshot}`` trial input file.

    The plan passes the RAES plan ingress gate. Family trial admission later
    binds the plan entry, the installed family and the snapshot bytes.
    """
    from raes_contracts.canonical import canonical_json_bytes
    from raes_contracts.contracts.admitted_trial_plan_ingress import (
        parse_admitted_trial_plan_json,
    )

    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_TRIAL_UNIT_BYTES:
        raise ValueError("--trial-input must be a regular file within the size limit")
    document = json.loads(path.read_bytes())
    if not isinstance(document, dict) or set(document) != {"plan", "plan_entry_id", "snapshot"}:
        raise ValueError("--trial-input must contain only plan, plan_entry_id and snapshot")
    entry = document["plan_entry_id"]
    if not isinstance(entry, str) or not _IDENTIFIER.fullmatch(entry):
        raise ValueError("--trial-input plan entry ID is invalid")
    plan = parse_admitted_trial_plan_json(canonical_json_bytes(document["plan"]))
    if entry not in plan.entries:
        raise ValueError("--trial-input plan has no such entry")
    return TrialUnit(plan, entry, canonical_json_bytes(document["snapshot"]))
