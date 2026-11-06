"""Compose and run the trial that a started lab's SDL declares (#1670)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from aptl.core.trial_attempt import TrialAttempt
from aptl.core.trial_record import TrialRecord

__all__ = ["run_lab_trial", "trial_summary"]


def run_lab_trial(
    project_dir: Path,
    attempt: TrialAttempt,
    *,
    progress: Callable[[str], None],
) -> TrialRecord:
    """Run the declared participants on the started lab and seal the run."""
    raise RuntimeError("trial runs are not supported")


def trial_summary(record: TrialRecord) -> dict[str, object]:
    """Return the JSON fields that ``lab start --json`` reports for a trial."""
    return {
        "run_id": record.run_id,
        "attempt_id": record.attempt_id,
        "terminal_cause": record.terminal_cause,
        "participants": [
            {"address": item.address, "status": item.status} for item in record.participants
        ],
    }
