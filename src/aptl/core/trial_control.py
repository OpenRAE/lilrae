"""The durable fence and stop request of one lab-start trial (#1670).

Startup claims the existing trial fence for the attempt while it still holds
the lifecycle lock. Other lifecycle operations then refuse until the trial
releases the fence after its seal. ``lab stop`` records a stop request that the
running trial observes, then waits for the release.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from aptl.core.trial_attempt import TrialAttempt
from aptl.core.trial_ownership import TRIAL_FENCE, claim_trial_owner, trial_fence_owner
from aptl.utils.pathsafe import (
    REASON_NOT_FOUND,
    PathContainmentError,
    create_exclusive_nofollow,
    open_contained_nofollow,
    remove_contained_nofollow,
)

__all__ = ["ActiveTrial", "TrialControl", "trial_owner"]

_RECORDS = Path(".aptl/trial")
_ATTEMPT = _RECORDS / "attempt.json"
_RUNNER = _RECORDS / "runner.json"
_STOP = _RECORDS / "stop-request.json"
_MAX_RECORD_BYTES = 4096


@dataclass(frozen=True)
class ActiveTrial:
    """The fenced attempt and the process that runs it, if it started."""

    pid: int | None
    run_id: str
    attempt_id: str


def trial_owner(attempt: TrialAttempt | ActiveTrial) -> bytes:
    """Return the fence identity of one attempt from its run and attempt IDs."""
    identity = json.dumps([attempt.run_id, attempt.attempt_id]).encode()
    return hashlib.sha256(identity).hexdigest().encode()


class TrialControl:
    """Fence, process and stop-request records for one project's trial."""

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root

    def claim(self, attempt: TrialAttempt) -> None:
        """Claim the durable trial fence; the caller holds the lifecycle lock."""
        self._records_dir()
        claim_trial_owner(self._project_root, trial_owner(attempt))
        for record in (_RUNNER, _STOP):
            self._remove(record)
        self._remove(_ATTEMPT)
        self._write_once(_ATTEMPT, {"run_id": attempt.run_id, "attempt_id": attempt.attempt_id})

    def begin(self, attempt: TrialAttempt) -> None:
        """Record this process as the runner of the fenced attempt."""
        self._require_fenced(attempt)
        self._write_once(_RUNNER, {"pid": os.getpid()})

    def release(self, attempt: TrialAttempt | ActiveTrial) -> None:
        """Remove the stop and process records, then the fence of the attempt."""
        self._require_fenced(attempt)
        for record in (_STOP, _RUNNER, _ATTEMPT):
            self._remove(record)
        self._remove(TRIAL_FENCE)

    def active(self) -> ActiveTrial | None:
        """Return the fenced attempt and its process, if a trial is fenced."""
        attempt = self._read(_ATTEMPT)
        if attempt is None or trial_fence_owner(self._project_root) is None:
            return None
        runner = self._read(_RUNNER) or {}
        pid = runner.get("pid")
        return ActiveTrial(
            pid=pid if type(pid) is int else None,
            run_id=str(attempt.get("run_id")),
            attempt_id=str(attempt.get("attempt_id")),
        )

    def runner_alive(self) -> bool:
        """Return whether the recorded runner process still exists."""
        current = self.active()
        if current is None or current.pid is None or current.pid <= 0:
            return False
        try:
            os.kill(current.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def request_stop(self) -> ActiveTrial | None:
        """Record a stop request for the fenced attempt and return it."""
        current = self.active()
        if current is None:
            return None
        if self._read(_STOP) is None:
            self._write_once(
                _STOP, {"run_id": current.run_id, "attempt_id": current.attempt_id}
            )
        return current

    def stop_requested(self) -> bool:
        """Return whether a stop request exists for the fenced attempt."""
        current = self.active()
        request = self._read(_STOP)
        return (
            current is not None
            and request is not None
            and request.get("run_id") == current.run_id
            and request.get("attempt_id") == current.attempt_id
        )

    def _require_fenced(self, attempt: TrialAttempt | ActiveTrial) -> None:
        if trial_fence_owner(self._project_root) != trial_owner(attempt):
            raise RuntimeError("the trial fence belongs to another attempt")

    def _records_dir(self) -> None:
        directory = self._project_root / _RECORDS
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        (self._project_root / TRIAL_FENCE.parent).mkdir(mode=0o700, parents=True, exist_ok=True)

    def _read(self, record: Path) -> dict[str, object] | None:
        try:
            with open_contained_nofollow(self._project_root, record) as source:
                data = source.read(_MAX_RECORD_BYTES + 1)
        except PathContainmentError as exc:
            if exc.reason == REASON_NOT_FOUND:
                return None
            raise
        if len(data) > _MAX_RECORD_BYTES:
            raise RuntimeError("trial control record is too large")
        try:
            value = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RuntimeError("trial control record is invalid") from None
        if not isinstance(value, dict):
            raise RuntimeError("trial control record is invalid")
        return value

    def _write_once(self, record: Path, value: dict[str, object]) -> None:
        self._records_dir()
        create_exclusive_nofollow(self._project_root, record, json.dumps(value).encode())

    def _remove(self, record: Path) -> None:
        try:
            remove_contained_nofollow(self._project_root, record)
        except PathContainmentError as exc:
            if exc.reason != REASON_NOT_FOUND:
                raise
