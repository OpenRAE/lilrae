"""The durable fence and stop request of one lab-start trial (#1670).

Startup claims the existing trial fence for the attempt while it still holds
the lifecycle lock. Other lifecycle operations then refuse until the trial
releases the fence after its seal. ``lab stop`` records a stop request that the
running trial observes, then waits for the release.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aptl.core.trial_attempt import TrialAttempt

__all__ = ["ActiveTrial", "TrialControl", "trial_owner"]


@dataclass(frozen=True)
class ActiveTrial:
    """The running trial's process and attempt identity."""

    pid: int
    run_id: str
    attempt_id: str


def trial_owner(attempt: TrialAttempt) -> bytes:
    """Return the fence identity of one attempt."""
    raise RuntimeError("trial ownership is not supported")


class TrialControl:
    """Fence, process and stop-request records for one project's trial."""

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root

    def claim(self, attempt: TrialAttempt) -> None:
        """Claim the durable trial fence; the caller holds the lifecycle lock."""
        raise RuntimeError("trial control is not supported")

    def begin(self, attempt: TrialAttempt) -> None:
        """Record this process as the runner of the fenced attempt."""
        raise RuntimeError("trial control is not supported")

    def release(self, attempt: TrialAttempt) -> None:
        """Remove the stop and process records, then the fence of the attempt."""
        raise RuntimeError("trial control is not supported")

    def active(self) -> ActiveTrial | None:
        """Return the fenced attempt and its process, if a trial is fenced."""
        raise RuntimeError("trial control is not supported")

    def runner_alive(self) -> bool:
        """Return whether the recorded runner process still exists."""
        raise RuntimeError("trial control is not supported")

    def request_stop(self) -> ActiveTrial | None:
        """Record a stop request for the fenced attempt and return it."""
        raise RuntimeError("trial control is not supported")

    def stop_requested(self) -> bool:
        """Return whether a stop request exists for the fenced attempt."""
        raise RuntimeError("trial control is not supported")
