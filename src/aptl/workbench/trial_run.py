"""Run the declared participants of one trial until they end, the deadline, or a stop."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from threading import Event
from typing import Protocol

from raes_contracts.runtime_state import ApplyResult
from raes_processor.models import ParticipantAutonomousExecutionRuntime

from aptl.backends.lilrae_participant_execution import LilraeParticipantExecution
from aptl.core.participant_binding import LilraeParticipantBinding
from aptl.core.runstore import LocalRunStore
from aptl.core.trial_attempt import TrialAttempt
from aptl.core.trial_record import TrialParticipantRecord, TrialRecord
from aptl.core.trial_sdl import DeclaredParticipant
from aptl.utils.redaction import redact

__all__ = [
    "DeclaredTrial",
    "NativeTrialRelease",
    "ParticipantInvocation",
    "SteppedRuntime",
    "TrialSupervision",
    "native_participant_address",
    "run_declared_trial",
]

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


class SteppedRuntime(Protocol):
    """The started runtime operation that releases the admitted scheduler batch."""

    def advance_time(self, clock_address: str, *, ticks: int) -> ApplyResult: ...


@dataclass(frozen=True)
class NativeTrialRelease:
    """The started runtime, its native participant owner and the release policy."""

    runtime: SteppedRuntime
    native: LilraeParticipantExecution
    policy: ParticipantAutonomousExecutionRuntime


@dataclass(frozen=True)
class TrialSupervision:
    """The stop signal, clock and polling interval that supervise one trial."""

    stop_requested: Callable[[], bool]
    clock: Clock
    poll_seconds: float = 0.2


def native_participant_address(binding: LilraeParticipantBinding) -> str:
    """Return the SDL agent address of one installed native participant binding."""
    return "agents." + binding.implementation_selection.participant_address.removeprefix(
        "participant.behavior."
    )


class _RecordedInvocation:
    """Record the native call; selection, concurrency and tools remain RAE-owned."""

    def __init__(
        self,
        invocation: ParticipantInvocation,
        outcome: _Outcome,
        clock: Clock,
        native: LilraeParticipantExecution,
        stop_peer: bool,
    ) -> None:
        self.invocation, self.outcome, self.clock = invocation, outcome, clock
        self.native, self.stop_peer = native, stop_peer

    @property
    def configuration_result(self) -> object | None:
        """Return the wrapped executor's configuration result, if it has one."""
        return getattr(self.invocation, "configuration_result", None)

    @property
    def tool_inventory(self) -> frozenset[tuple[str, str]]:
        """Return the wrapped executor's tool inventory, or no tools."""
        return getattr(self.invocation, "tool_inventory", frozenset())

    @property
    def timeout_seconds(self) -> int:
        """Return the wrapped executor's admitted timeout."""
        return self.invocation.timeout_seconds

    def _call(self, operation: Callable[[], str]) -> str:
        """Run one native operation and record its times, output or failure."""
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

    def __call__(self, action_id: str, cancellation: Event) -> str:
        """Invoke the wrapped executor without scheduler-issued tools."""
        return self._call(lambda: self.invocation(action_id, cancellation))

    def invoke_with_tools(
        self, action_id: str, cancellation: Event, tools: object
    ) -> str:
        """Invoke the wrapped executor with the scheduler-issued tool port."""
        return self._call(
            lambda: self.invocation.invoke_with_tools(
                action_id, cancellation, tools
            )
        )


def run_declared_trial(
    trial: DeclaredTrial,
    *,
    release: NativeTrialRelease,
    invocations: Mapping[str, ParticipantInvocation],
    evidence: Mapping[str, Mapping[str, object]],
    store: LocalRunStore,
    supervision: TrialSupervision,
) -> TrialRecord:
    """Release one admitted native scheduler batch after participant and capture readiness."""
    episode_seconds = _bounded_episode(trial, invocations)
    outcomes = {item.address: _Outcome() for item in trial.participants}
    _install_recorders(release, invocations, outcomes, supervision.clock)
    started = supervision.clock()
    cause = _release_and_drain(
        trial,
        release,
        supervision,
        started + timedelta(seconds=episode_seconds),
    )
    records = tuple(
        _participant_record(
            store,
            trial.attempt,
            item,
            invocations[item.address].prompt_sha256,
            outcomes[item.address],
            evidence.get(item.address, {}),
            cause,
        )
        for item in trial.participants
    )
    return TrialRecord(
        run_id=trial.attempt.run_id,
        attempt_id=trial.attempt.attempt_id,
        scenario_sha256=trial.scenario_sha256,
        deadline=_timestamp(trial.attempt.deadline),
        started_at=_timestamp(started),
        ended_at=_timestamp(supervision.clock()),
        terminal_cause=_terminal_cause(cause, records),
        participants=records,
    )


def _bounded_episode(
    trial: DeclaredTrial, invocations: Mapping[str, ParticipantInvocation]
) -> int:
    """Return the episode length after each declared participant has one invocation."""
    participants = trial.participants
    if not participants or {item.address for item in participants} != set(invocations):
        raise ValueError("every declared trial participant needs one invocation")
    if trial.episode_seconds is None or trial.episode_seconds < 1:
        raise ValueError("the admitted trial has no bounded episode")
    return trial.episode_seconds


def _install_recorders(
    release: NativeTrialRelease,
    invocations: Mapping[str, ParticipantInvocation],
    outcomes: Mapping[str, _Outcome],
    clock: Clock,
) -> None:
    """Replace each admitted executor with its recording wrapper before dispatch."""
    native = release.native
    stop_peer = release.policy.failure_policy == "stop"
    installed = []
    for binding in native.bindings:
        address = native_participant_address(binding)
        executor = _RecordedInvocation(
            invocations[address], outcomes[address], clock, native, stop_peer
        )
        installed.append(replace(binding, executor=executor))
    native.install_before_dispatch(tuple(installed))


def _release_and_drain(
    trial: DeclaredTrial,
    release: NativeTrialRelease,
    supervision: TrialSupervision,
    episode_end: datetime,
) -> str:
    """Advance the clock once, then drain native work; return the trial's cause."""
    ended = Event()
    cause = ["completed"]
    watcher = threading.Thread(
        target=_watch_stop,
        args=(trial.attempt.deadline, episode_end, release, supervision, ended, cause),
        name="trial-stop",
        daemon=True,
    )
    watcher.start()
    try:
        result = release.runtime.advance_time(release.policy.clock_address, ticks=1)
        if not result.success and cause[0] == "completed":
            cause[0] = "failed"
    finally:
        ended.set()
        watcher.join()
        release.native.cancel()
        if not release.native.drain(_DRAIN_SECONDS):
            raise RuntimeError(
                "native participants did not stop before capture finalization"
            )
    return cause[0]


def _watch_stop(
    deadline: datetime,
    episode_end: datetime,
    release: NativeTrialRelease,
    supervision: TrialSupervision,
    ended: Event,
    cause: list[str],
) -> None:
    """Cancel native work at a stop request, the deadline or the episode end."""
    # This supervises one native operation; the RAE scheduler dispatches roles.
    while not ended.wait(supervision.poll_seconds):
        reason = _stop_reason(deadline, episode_end, supervision)
        if reason is not None:
            cause[0] = reason
            release.native.cancel()
            return


def _stop_reason(
    deadline: datetime, episode_end: datetime, supervision: TrialSupervision
) -> str | None:
    """Return the first reached stop condition, in priority order, or ``None``."""
    now = supervision.clock()
    reached = (
        ("stopped", supervision.stop_requested()),
        ("deadline", now >= deadline),
        (_EPISODE_END, now >= episode_end),
    )
    return next((reason for reason, hit in reached if hit), None)


def _terminal_cause(
    cause: str, records: tuple[TrialParticipantRecord, ...]
) -> str:
    """Map the supervisor's cause and participant results to the trial's end."""
    terminal = "completed" if cause == _EPISODE_END else cause
    if terminal == "completed" and any(item.status == "failed" for item in records):
        return "failed"
    return terminal


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
