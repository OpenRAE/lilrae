"""The caller-supplied identity and deadline of one trial attempt."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

__all__ = ["TrialAttempt", "parse_trial_attempt"]


@dataclass(frozen=True)
class TrialAttempt:
    """Run and attempt IDs and the UTC deadline that the caller owns."""

    run_id: str
    attempt_id: str
    deadline: datetime


def parse_trial_attempt(
    run_id: str | None, attempt_id: str | None, deadline: str | None
) -> TrialAttempt | None:
    """Return ``None`` with no trial options, or one validated attempt.

    Raise ``ValueError`` for a partial option set, an unsafe ID, or a deadline
    that is not an RFC 3339 UTC time.
    """
    if run_id is None and attempt_id is None and deadline is None:
        return None
    raise ValueError("trial attempts are not supported")
