"""Generated interleavings compare real adapter effects with an independent oracle."""

from threading import Event

import pytest
from hypothesis import settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from aptl.backends.lilrae_participant_action_model import violations
from aptl.backends.lilrae_participant_tools import LilraeToolSession
from aptl.workbench.process import AgentExecutionError
from tests.test_lilrae_participant_tools import binding, port, result


class ToolSessions(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.ports = [port(), port()]
        self.signals = [Event(), Event()]
        for index, authority in enumerate(self.ports):
            authority.participant_address = f"participant.behavior.red-{index}"
            authority.invocation_action_instance_id = f"outer-{index}"
            authority.episode_id = f"episode-{index}"
        self.sessions = [
            LilraeToolSession(p, (binding(),), signal)
            for p, signal in zip(self.ports, self.signals, strict=True)
        ]
        self.closed = [False, False]
        self.effects = set()
        self.pending = {}

    @rule(who=st.integers(0, 1), identifier=st.integers(0, 3), valid=st.booleans())
    def attempt(self, who, identifier, valid):
        key = (who, identifier)
        permitted = (
            valid
            and not self.closed[who]
            and not self.signals[who].is_set()
            and key not in self.effects
        )
        try:
            call = self.sessions[who].begin(
                "aptl-red",
                "kali_run_command",
                {"command": "id" if valid else "different"},
                str(identifier),
            )
        except AgentExecutionError:
            assert not permitted
        else:
            # The independent native-effect recorder is reached only when the
            # actual adapter returns a consumed dispatch grant.
            assert permitted
            self.effects.add(key)
            self.pending[key] = call

    @rule(who=st.integers(0, 1), identifier=st.integers(0, 3), unknown=st.booleans())
    def finish(self, who, identifier, unknown):
        call = self.pending.pop((who, identifier), None)
        if call is None:
            return
        if unknown:
            self.sessions[who].unknown(call)
        else:
            try:
                self.sessions[who].complete(call, result())
            except AgentExecutionError:
                assert self.closed[who] or self.signals[who].is_set()

    @rule(who=st.integers(0, 1))
    def cancel(self, who):
        self.signals[who].set()

    @rule(who=st.integers(0, 1))
    def close(self, who):
        self.sessions[who].close()
        self.closed[who] = True

    @invariant()
    def effects_and_authority_match(self):
        for who, (session, authority) in enumerate(
            zip(self.sessions, self.ports, strict=True)
        ):
            assert not any(violations(state) for state in session.states())
            assert authority.dispatch.call_count == sum(
                index == who for index, _ in self.effects
            )
            assert len(session.states()) == sum(
                index == who for index, _ in self.effects
            )
            assert all(
                call.args[0].participant_address == authority.participant_address
                for call in authority.admit.call_args_list
            )

    def teardown(self):
        for session in self.sessions:
            session.close()


TestToolSessions = ToolSessions.TestCase
TestToolSessions.settings = settings(
    max_examples=60, stateful_step_count=40, deadline=None
)
TestToolSessions = pytest.mark.fuzz(TestToolSessions)
