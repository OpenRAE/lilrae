"""Run the declared participants of one trial until they end, the deadline, or a stop."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Event
from typing import Protocol

from aptl.core.runstore import LocalRunStore
from aptl.core.trial_attempt import TrialAttempt
from aptl.core.trial_record import TrialParticipantRecord, TrialRecord
from aptl.core.trial_sdl import DeclaredParticipant
from aptl.utils.redaction import redact

__all__ = ["DeclaredTrial", "ParticipantInvocation", "run_declared_trial"]

_OUTPUT_DIR = "trial/participants"
# A cancelled child gets this long to exit before the trial seals without it.
_DRAIN_SECONDS = 60.0
# The supervisor's cause when the shared episode ended; the trial completed.
_EPISODE_END = "episode-end"

Clock = Callable[[], datetime]


class ParticipantInvocation(Protocol):
    """One managed participant invocation that honors a cancellation event."""

    @property
    def prompt_sha256(self) -> str: ...

    def __call__(self, action_id: str, cancellation: Event) -> str: ...


@dataclass(frozen=True)
class DeclaredTrial:
    """The caller's attempt, the trial SDL digest, and its declared participants.

    ``episode_seconds`` is the trial's normal length; ``None`` runs to the deadline.
    """

    attempt: TrialAttempt
    scenario_sha256: str
    participants: tuple[DeclaredParticipant, ...]
    episode_seconds: int | None = None


@dataclass
class _Outcome:
    """What one invocation returned or raised, and when."""

    started_at: str | None = None
    ended_at: str | None = None
    output: str | None = None
    failure: str | None = None


class _RecordedInvocation:
    """Record the native call; selection, concurrency and tools remain RAE-owned."""

    def __init__(self, invocation, outcome, clock, native, stop_peer):
        self.invocation, self.outcome, self.clock = invocation, outcome, clock
        self.native, self.stop_peer = native, stop_peer

    @property
    def configuration_result(self):
        return getattr(self.invocation, "configuration_result", None)

    @property
    def tool_inventory(self):
        return getattr(self.invocation, "tool_inventory", frozenset())

    @property
    def timeout_seconds(self):
        return self.invocation.timeout_seconds

    def _call(self, operation):
        self.outcome.started_at = _timestamp(self.clock())
        try:
            self.outcome.output = operation()
            return self.outcome.output
        except Exception as exc:
            self.outcome.failure = redact(str(exc)) or type(exc).__name__
            if self.stop_peer:
                self.native.cancel()
            raise
        finally:
            self.outcome.ended_at = _timestamp(self.clock())

    def __call__(self, action_id, cancellation):
        return self._call(lambda: self.invocation(action_id, cancellation))

    def invoke_with_tools(self, action_id, cancellation, tools):
        return self._call(
            lambda: self.invocation.invoke_with_tools(action_id, cancellation, tools)
        )


def run_declared_trial(
    trial: DeclaredTrial,
    *,
    runtime,
    native,
    policy,
    invocations: Mapping[str, ParticipantInvocation],
    evidence: Mapping[str, Mapping[str, object]],
    stop_requested: Callable[[], bool],
    store: LocalRunStore,
    clock: Clock,
    poll_seconds: float = 0.2,
) -> TrialRecord:
    """Release one admitted native scheduler batch after participant and capture readiness."""
    from dataclasses import replace

    participants = trial.participants
    if not participants or {item.address for item in participants} != set(invocations):
        raise ValueError("every declared trial participant needs one invocation")
    if trial.episode_seconds is None or trial.episode_seconds < 1:
        raise ValueError("the admitted trial has no bounded episode")
    outcomes = {item.address: _Outcome() for item in participants}
    installed = []
    for binding in native.bindings:
        address = (
            "agents."
            + binding.implementation_selection.participant_address.removeprefix(
                "participant.behavior."
            )
        )
        installed.append(
            replace(
                binding,
                executor=_RecordedInvocation(
                    invocations[address],
                    outcomes[address],
                    clock,
                    native,
                    policy.failure_policy == "stop",
                ),
            )
        )
    native.install_before_dispatch(tuple(installed))
    started = clock()
    episode_end = started + timedelta(seconds=trial.episode_seconds)
    ended = Event()
    cause = ["completed"]

    def watch_stop():
        # This supervises one native operation; the RAE scheduler dispatches roles.
        while not ended.wait(poll_seconds):
            now = clock()
            if stop_requested():
                cause[0] = "stopped"
            elif now >= trial.attempt.deadline:
                cause[0] = "deadline"
            elif now >= episode_end:
                cause[0] = _EPISODE_END
            else:
                continue
            native.cancel()
            return

    watcher = threading.Thread(target=watch_stop, name="trial-stop", daemon=True)
    watcher.start()
    try:
        result = runtime.advance_time(policy.clock_address, ticks=1)
        if not result.success and cause[0] == "completed":
            cause[0] = "failed"
    finally:
        ended.set()
        watcher.join()
        native.cancel()
        if not native.drain(_DRAIN_SECONDS):
            raise RuntimeError(
                "native participants did not stop before capture finalization"
            )
    records = tuple(
        _participant_record(
            store,
            trial.attempt,
            item,
            invocations[item.address].prompt_sha256,
            outcomes[item.address],
            evidence.get(item.address, {}),
            cause[0],
        )
        for item in participants
    )
    terminal = "completed" if cause[0] == _EPISODE_END else cause[0]
    if terminal == "completed" and any(item.status == "failed" for item in records):
        terminal = "failed"
    return TrialRecord(
        run_id=trial.attempt.run_id,
        attempt_id=trial.attempt.attempt_id,
        scenario_sha256=trial.scenario_sha256,
        deadline=_timestamp(trial.attempt.deadline),
        started_at=_timestamp(started),
        ended_at=_timestamp(clock()),
        terminal_cause=terminal,
        participants=records,
    )


def _participant_record(
    store: LocalRunStore,
    attempt: TrialAttempt,
    participant: DeclaredParticipant,
    prompt_sha256: str,
    outcome: _Outcome,
    evidence: Mapping[str, object],
    cause: str,
) -> TrialParticipantRecord:
    """Write the participant's redacted output and return its record."""
    output_path = None
    if outcome.output is not None:
        name = hashlib.sha256(participant.address.encode()).hexdigest()[:16]
        output_path = f"{_OUTPUT_DIR}/{participant.agent}-{name}.txt"
        store.write_file(attempt.run_id, output_path, redact(outcome.output).encode())
    if outcome.started_at is not None and outcome.ended_at is None:
        outcome.failure = (
            f"participant did not stop within {_DRAIN_SECONDS:.0f} seconds"
        )
    status = _status(outcome, cause)
    return TrialParticipantRecord(
        address=participant.address,
        role=participant.role,
        model=participant.model,
        context_assets=participant.context_assets,
        prompt_sha256=prompt_sha256,
        status=status,
        started_at=outcome.started_at,
        ended_at=outcome.ended_at,
        failure=outcome.failure if status != "completed" else None,
        output_path=output_path,
        invocation=dict(evidence),
    )


def _status(outcome: _Outcome, cause: str) -> str:
    """Classify one participant from its outcome and the trial's end."""
    if outcome.started_at is None:
        return "not-started"
    if outcome.failure is None and outcome.output is not None:
        return "completed"
    return "cancelled" if cause in {"deadline", "stopped", _EPISODE_END} else "failed"


def _timestamp(value: datetime) -> str:
    """Render one UTC time in RFC 3339 form with a ``Z`` suffix."""
    return value.isoformat().replace("+00:00", "Z")
