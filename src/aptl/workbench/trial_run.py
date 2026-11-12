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


def run_declared_trial(
    trial: DeclaredTrial,
    *,
    invocations: Mapping[str, ParticipantInvocation],
    evidence: Mapping[str, Mapping[str, object]],
    stop_requested: Callable[[], bool],
    store: LocalRunStore,
    clock: Clock,
    poll_seconds: float = 1.0,
) -> TrialRecord:
    """Start every participant and stop them at the episode end, the deadline, or on request.

    The episode end is the trial's normal end: a participant cancelled there completed.

    The returned record is not sealed. The caller drains credentials and
    capture first, records their cleanup, and then seals the run.
    """
    participants = trial.participants
    if not participants or {item.address for item in participants} != set(invocations):
        raise ValueError("every declared trial participant needs one invocation")
    started_at = _timestamp(clock())
    cancellation = Event()
    outcomes = {item.address: _Outcome() for item in participants}
    threads = [
        threading.Thread(
            target=_invoke,
            args=(
                trial.attempt,
                item,
                invocations[item.address],
                cancellation,
                outcomes[item.address],
                clock,
            ),
            name=f"trial-{item.agent}",
            daemon=True,
        )
        for item in participants
    ]
    for thread in threads:
        thread.start()
    episode_end = (
        None
        if trial.episode_seconds is None
        else clock() + timedelta(seconds=trial.episode_seconds)
    )
    cause = _supervise(
        threads, trial.attempt, stop_requested, clock, poll_seconds, episode_end
    )
    cancellation.set()
    for thread in threads:
        thread.join(_DRAIN_SECONDS)
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
        for item in participants
    )
    if cause == _EPISODE_END:
        cause = "completed"
    if cause == "completed" and any(item.status == "failed" for item in records):
        cause = "failed"
    return TrialRecord(
        run_id=trial.attempt.run_id,
        attempt_id=trial.attempt.attempt_id,
        scenario_sha256=trial.scenario_sha256,
        deadline=_timestamp(trial.attempt.deadline),
        started_at=started_at,
        ended_at=_timestamp(clock()),
        terminal_cause=cause,
        participants=records,
    )


def _supervise(
    threads: list[threading.Thread],
    attempt: TrialAttempt,
    stop_requested: Callable[[], bool],
    clock: Clock,
    poll_seconds: float,
    episode_end: datetime | None,
) -> str:
    """Wait for every participant, the episode end, the deadline, or a stop request."""
    cause = None
    while cause is None and any(thread.is_alive() for thread in threads):
        cause = _stop_cause(attempt, stop_requested(), clock(), episode_end)
        if cause is None:
            _join_slice(threads, attempt, clock(), poll_seconds, episode_end)
    return cause or "completed"


def _stop_cause(
    attempt: TrialAttempt,
    stop_requested: bool,
    now: datetime,
    episode_end: datetime | None,
) -> str | None:
    """Return why the trial stops now, or ``None`` while it keeps running."""
    if stop_requested:
        return "stopped"
    if now >= attempt.deadline:
        return "deadline"
    return _EPISODE_END if episode_end is not None and now >= episode_end else None


def _join_slice(
    threads: list[threading.Thread],
    attempt: TrialAttempt,
    now: datetime,
    poll_seconds: float,
    episode_end: datetime | None,
) -> None:
    """Wait one poll interval, never past the deadline or the episode end."""
    remaining = (attempt.deadline - now).total_seconds()
    if episode_end is not None:
        remaining = min(remaining, max((episode_end - now).total_seconds(), 0.0))
    for thread in threads:
        thread.join(min(poll_seconds, remaining) / max(len(threads), 1))


def _invoke(
    attempt: TrialAttempt,
    participant: DeclaredParticipant,
    invocation: ParticipantInvocation,
    cancellation: Event,
    outcome: _Outcome,
    clock: Clock,
) -> None:
    """Run one invocation and keep its output or failure, never its credentials."""
    outcome.started_at = _timestamp(clock())
    try:
        outcome.output = invocation(
            f"{attempt.attempt_id}-{participant.agent}", cancellation
        )
    except Exception as exc:
        # A participant failure is a recorded outcome, not a trial failure.
        outcome.failure = redact(str(exc)) or type(exc).__name__
    finally:
        outcome.ended_at = _timestamp(clock())


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
    if (outcome.failure is None and outcome.output is not None) or (
        cause == _EPISODE_END and outcome.ended_at is not None
    ):
        return "completed"
    return "cancelled" if cause in {"deadline", "stopped"} else "failed"


def _timestamp(value: datetime) -> str:
    """Render one UTC time in RFC 3339 form with a ``Z`` suffix."""
    return value.isoformat().replace("+00:00", "Z")
