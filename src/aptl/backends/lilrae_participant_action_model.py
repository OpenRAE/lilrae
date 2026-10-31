"""Executable refinement of the native adapter, not a second RAES lifecycle.

RAES receipts justify ADMIT, DISPATCH and settlement events. COMMIT is observed
only from the owning scheduler's accepted history, never inferred from a tool
response. This finite model claims neither host isolation nor unbounded proof.
"""

from dataclasses import dataclass, replace
from enum import StrEnum


class Phase(StrEnum):
    PROPOSED = "proposed"
    REFUSED = "refused"
    ADMITTED = "admitted"
    DISPATCHED = "dispatched"
    COMPLETED = "completed"
    WITHHELD = "withheld"
    INDETERMINATE = "indeterminate"


class Event(StrEnum):
    ADMIT = "admit"
    REFUSE = "refuse"
    DISPATCH = "dispatch"
    COMPLETE = "complete"
    WITHHOLD = "withhold"
    UNKNOWN = "unknown"
    DELIVER = "deliver"
    COMMIT = "commit"


@dataclass(frozen=True)
class ActionState:
    phase: Phase = Phase.PROPOSED
    admitted: bool = False
    dispatches: int = 0
    delivered: bool = False
    committed: bool = False


_TRANSITIONS = {
    (Phase.PROPOSED, Event.ADMIT): Phase.ADMITTED,
    (Phase.PROPOSED, Event.REFUSE): Phase.REFUSED,
    (Phase.ADMITTED, Event.DISPATCH): Phase.DISPATCHED,
    (Phase.ADMITTED, Event.WITHHOLD): Phase.WITHHELD,
    (Phase.DISPATCHED, Event.COMPLETE): Phase.COMPLETED,
    (Phase.DISPATCHED, Event.UNKNOWN): Phase.INDETERMINATE,
}
_SETTLED = frozenset({Phase.COMPLETED, Phase.WITHHELD, Phase.INDETERMINATE})


def violations(state: ActionState) -> tuple[str, ...]:
    """Safety predicates independent of the transition table."""
    checks = (
        (state.dispatches > 0 and not state.admitted, "effect_without_admission"),
        (state.dispatches not in (0, 1), "repeated_effect"),
        (state.phase == Phase.WITHHELD and state.dispatches != 0, "withheld_effect"),
        (
            state.phase in {Phase.DISPATCHED, Phase.COMPLETED, Phase.INDETERMINATE}
            and state.dispatches != 1,
            "missing_dispatch",
        ),
        (
            state.delivered and state.phase == Phase.INDETERMINATE,
            "unknown_delivered",
        ),
        (state.delivered and state.phase != Phase.COMPLETED, "unsettled_delivery"),
        (state.committed and state.phase not in _SETTLED, "history_without_settlement"),
        (
            state.phase in _SETTLED and not state.admitted,
            "settlement_without_admission",
        ),
    )
    return tuple(code for invalid, code in checks if invalid)


def advance(state: ActionState, event: Event) -> ActionState:
    """Refuse invalid adapter transitions before the caller performs effects."""
    if violations(state):
        raise ValueError("invalid participant action state")
    if event == Event.COMMIT and state.phase in _SETTLED and not state.committed:
        return replace(state, committed=True)
    if (
        event == Event.DELIVER
        and state.phase == Phase.COMPLETED
        and not state.delivered
    ):
        return replace(state, delivered=True)
    phase = _TRANSITIONS.get((state.phase, event))
    if phase is None:
        raise ValueError("participant action transition refused")
    result = replace(
        state,
        phase=phase,
        admitted=state.admitted or event == Event.ADMIT,
        dispatches=state.dispatches + (event == Event.DISPATCH),
    )
    if violations(result):
        raise ValueError("participant action invariant violated")
    return result
