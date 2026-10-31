"""Bounded architectural safety, including negative controls for the checker."""

from dataclasses import replace
from itertools import product

import pytest

from aptl.backends.lilrae_participant_action_model import (
    ActionState,
    Event,
    Phase,
    advance,
    violations,
)


def successors(state):
    for event in Event:
        try:
            yield event, advance(state, event)
        except ValueError:
            pass


def test_all_two_call_interleavings_preserve_authority_and_peer_history():
    initial = (ActionState(), ActionState())
    pending, seen = [initial], {initial}
    while pending:
        pair = pending.pop()
        assert all(not violations(state) for state in pair)
        for index in (0, 1):
            for event, successor in successors(pair[index]):
                updated = list(pair)
                updated[index] = successor
                assert updated[1 - index] == pair[1 - index]
                candidate = tuple(updated)
                if candidate not in seen:
                    seen.add(candidate)
                    pending.append(candidate)
    # All terminal pairs, including unknown/success, must be reachable.
    terminal = (Phase.COMPLETED, Phase.WITHHELD, Phase.INDETERMINATE)
    for left, right in product(terminal, repeat=2):
        assert any(
            a.phase == left and b.phase == right and a.committed and b.committed
            for a, b in seen
        )


@pytest.mark.parametrize(
    "mutant, expected",
    [
        (ActionState(phase=Phase.DISPATCHED, dispatches=1), "effect_without_admission"),
        (ActionState(admitted=True, dispatches=2), "repeated_effect"),
        (ActionState(phase=Phase.INDETERMINATE, delivered=True), "unknown_delivered"),
        (ActionState(committed=True), "history_without_settlement"),
    ],
)
def test_negative_controls_expose_unsafe_states(mutant, expected):
    assert expected in violations(mutant)


def test_unknown_and_completed_work_cannot_dispatch_again():
    state = advance(advance(ActionState(), Event.ADMIT), Event.DISPATCH)
    for event in (Event.COMPLETE, Event.UNKNOWN):
        terminal = advance(state, event)
        with pytest.raises(ValueError):
            advance(terminal, Event.DISPATCH)
        committed = advance(terminal, Event.COMMIT)
        assert committed.committed
        with pytest.raises(ValueError):
            advance(committed, Event.ADMIT)
        assert replace(committed, committed=False).phase == terminal.phase
