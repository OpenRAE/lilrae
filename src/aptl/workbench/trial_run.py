"""Run the declared participants of one trial until they end, the deadline, or a stop."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from threading import Event
from typing import Protocol

from aptl.core.runstore import LocalRunStore
from aptl.core.trial_attempt import TrialAttempt
from aptl.core.trial_record import TrialRecord
from aptl.core.trial_sdl import DeclaredParticipant

__all__ = ["ParticipantInvocation", "run_declared_trial"]


class ParticipantInvocation(Protocol):
    """One managed participant invocation that honors a cancellation event."""

    @property
    def prompt_sha256(self) -> str: ...

    def __call__(self, action_id: str, cancellation: Event) -> str: ...


def run_declared_trial(
    *,
    attempt: TrialAttempt,
    scenario_sha256: str,
    participants: tuple[DeclaredParticipant, ...],
    invocations: Mapping[str, ParticipantInvocation],
    evidence: Mapping[str, Mapping[str, object]],
    stop_requested: Callable[[], bool],
    store: LocalRunStore,
    clock: Callable[[], datetime],
    poll_seconds: float = 1.0,
) -> TrialRecord:
    """Start every participant and stop them at the deadline or on request.

    The returned record is not sealed. The caller drains credentials and
    capture first, records their cleanup, and then seals the run.
    """
    raise RuntimeError("trial runs are not supported")
