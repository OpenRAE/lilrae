"""Installed participant application at the existing trial-serving boundary."""

from typing import Protocol
from dataclasses import dataclass
from threading import Event
from collections.abc import Callable
from datetime import datetime, UTC

from raes_contracts.contracts import (
    ParticipantConfigurationResultModel,
    ParticipantAutonomousExecutionStateModel,
)
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_contracts.trial_unit import TrialUnitRequest
from aptl.core.agent_errors import AgentExecutionError
from aptl.core.participant_tools.contracts import ToolSession


@dataclass(frozen=True)
class TrialParticipantBounds:
    """Original wall deadline and an explicit shared-clock logical horizon."""

    started_at: datetime
    deadline: datetime
    logical_step_limit: int
    clock_steps: tuple[tuple[str, str, int], ...]
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def __post_init__(self) -> None:
        if (
            self.started_at.tzinfo is None
            or self.deadline.tzinfo is None
            or self.deadline <= self.started_at
            or type(self.logical_step_limit) is not int
            or not 1 <= self.logical_step_limit <= 10_000
            or any(
                type(ticks) is not int or ticks < 1 for _, _, ticks in self.clock_steps
            )
            or len({clock for clock, _, _ in self.clock_steps}) != len(self.clock_steps)
        ):
            raise ValueError("participant trial bounds are invalid")

    def time_exhausted(self) -> bool:
        now = self.clock()
        return not self.started_at <= now < self.deadline

    def refusal(self, snapshot: RuntimeSnapshot, participant: str) -> str | None:
        """Read scheduler-owned coordinates; never count requests or advance time."""
        if self.time_exhausted():
            return "Participant attempt deadline is exhausted."
        states = [
            ParticipantAutonomousExecutionStateModel.model_validate(row)
            for row in snapshot.participant_autonomous_execution_states.values()
            if row.get("participant_address") == participant
        ]
        if not states or snapshot.time_model_state is None:
            return "Participant logical clock is unavailable."
        limits = {clock: (policy, ticks) for clock, policy, ticks in self.clock_steps}
        for state in states:
            clock = snapshot.time_model_state.clocks.get(state.clock_address)
            expected = limits.get(state.clock_address)
            if (
                clock is None
                or expected is None
                or clock.progression_policy_address != expected[0]
                or clock.coordinate.segment != 0
            ):
                return "Participant logical clock is unavailable."
            elapsed = clock.coordinate.tick - clock.history[0].resulting.tick
            if elapsed < 0 or elapsed >= self.logical_step_limit * expected[1]:
                return "Participant logical step budget is exhausted."
        return None


class TrialParticipantApplication(Protocol):
    """Apply one exact attempt; retain its leases across pending deliveries."""

    def admit(self, request: TrialUnitRequest) -> None: ...

    def configure(self, request: TrialUnitRequest) -> None: ...

    def finish(self, request: TrialUnitRequest) -> None: ...


@dataclass(frozen=True)
class PendingTrialParticipant:
    """Admit an exact native offer without credentials or an executable process."""

    configuration_result: ParticipantConfigurationResultModel
    timeout_seconds: float
    tool_inventory: frozenset[tuple[str, str]] = frozenset()

    def __call__(self, action_id: str, cancellation: Event) -> str:
        raise AgentExecutionError("participant trial has not been configured")

    def invoke_with_tools(
        self, action_id: str, cancellation: Event, tools: ToolSession
    ) -> str:
        raise AgentExecutionError("participant trial has not been configured")
