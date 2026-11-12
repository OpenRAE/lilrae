"""The caller-supplied identity and deadline of one trial attempt."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

__all__ = ["TrialAttempt", "parse_trial_attempt"]

# The run store's identifier contract: a run ID names one run directory.
_IDENTIFIER = re.compile(r"^\w[\w.-]{0,127}$", re.ASCII)
_UTC_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")


@dataclass(frozen=True)
class TrialAttempt:
    """Run and attempt IDs and the UTC deadline that the caller owns."""

    run_id: str
    attempt_id: str
    deadline: datetime

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
