"""Local records that let ``lab stop`` request a running trial to stop."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aptl.core.trial_attempt import TrialAttempt

__all__ = ["ActiveTrial", "TrialControl"]


@dataclass(frozen=True)
class ActiveTrial:
    """The running trial's process and attempt identity."""

    pid: int
    run_id: str
    attempt_id: str


class TrialControl:
    """Private state-directory records for one active trial and its stop request."""

    def __init__(self, state_dir: Path) -> None:
        self._state_dir = state_dir

    def begin(self, attempt: TrialAttempt) -> None:
        """Record this process as the one active trial, or refuse a second one."""
        raise RuntimeError("trial control is not supported")

    def end(self) -> None:
        """Remove the active and stop records of this process's trial."""
        raise RuntimeError("trial control is not supported")

    def active(self) -> ActiveTrial | None:
        """Return the live active trial, if any."""
        raise RuntimeError("trial control is not supported")

    def request_stop(self) -> ActiveTrial | None:
        """Record a stop request for the live active trial and return it."""
        raise RuntimeError("trial control is not supported")

    def stop_requested(self) -> bool:
        """Return whether a stop request exists for the active trial."""
        raise RuntimeError("trial control is not supported")
