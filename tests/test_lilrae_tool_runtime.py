"""Tools run under the real RAES scheduler, preserving accepted peer histories."""

from threading import Barrier, Event

import pytest

from aptl.core.participant_tools.model import (
    Event as ModelEvent,
    advance,
    violations,
)
from tests.lilrae_tool_fixture import tool_scenario, tool_bindings
from tests.test_lilrae_concurrent_participants import manager_for
from tests.test_lilrae_participant_tools import result


class Controller:
    def __init__(self, role, rendezvous=None, blue_done=None):
        self.role = role
        self.rendezvous = rendezvous
        self.blue_done = blue_done
        self.effects = []
        self.states = ()

    def __call__(self, action, cancellation):
        pytest.fail("tool-enabled executor must receive the runtime session")

    def invoke_with_tools(self, action, cancellation, tools):
        server, tool, args = (
            ("aptl-red", "kali_run_command", {"command": "id"})
            if self.role == "red"
            else (
                "aptl-wazuh",
                "wazuh_api_request",
                {"endpoint": "/agents", "method": "GET"},
            )
        )

        def native(arguments):
            self.effects.append(arguments)
            if self.rendezvous:
                self.rendezvous.wait()
            if self.role == "red" and self.blue_done:
                assert self.blue_done.wait(15)
            if self.role == "blue" and self.blue_done:
                self.blue_done.set()
            return result()

        tools.invoke(server, tool, args, "call", native)
        self.states = tools.states()
        return self.role + " observed"


def test_real_scheduler_retains_both_tool_histories_when_blue_finishes_first():
    rendezvous, blue_done = Barrier(2, timeout=15), Event()
    controllers = {
        role: Controller(role, rendezvous, blue_done) for role in ("red", "blue")
    }
    manager, _ = manager_for(tool_bindings(controllers))
    with manager:
        applied = manager.apply(manager.plan(tool_scenario()))
        assert applied.success, applied.diagnostics
        for role, controller in controllers.items():
            assert len(controller.effects) == 1
            history = manager.snapshot.participant_behavior_history[
                "participant.behavior." + role
            ]
            assert len(history) == 6
            assert all(row.get("invocation_tool_context") for row in history[:3])
            assert not any(row.get("invocation_tool_context") for row in history[3:])
            assert all(
                not violations(advance(state, ModelEvent.COMMIT))
                for state in controller.states
            )


def test_changed_compiled_action_is_refused_before_any_native_work():
    controllers = {role: Controller(role) for role in ("red", "blue")}
    installed = tool_bindings(controllers)
    authored = tool_scenario()
    authored.action_contracts["native"].procedure_basis = "Changed semantics"
    manager, _ = manager_for(installed)
    with manager:
        plan = manager.plan(authored)
        assert any(
            item.code == "lilrae.tool-binding-refused" for item in plan.diagnostics
        )
        assert not manager.apply(plan).success
    assert not any(item.effects for item in controllers.values())


def test_unknown_tool_effects_keep_peer_history_and_do_not_reexecute():
    from raes_contracts.errors import ConflictError

    rendezvous = Barrier(2, timeout=15)

    class Uncertain(Controller):
        def invoke_with_tools(self, action, cancellation, tools):
            def native(args):
                self.effects.append(args)
                rendezvous.wait()
                raise TimeoutError("private-native-canary")

            tools.invoke(
                "aptl-red", "kali_run_command", {"command": "id"}, "call", native
            )
            raise AssertionError("unknown effects cannot report success")

    controllers = {"red": Uncertain("red"), "blue": Controller("blue", rendezvous)}
    manager, _ = manager_for(tool_bindings(controllers))
    with manager:
        applied = manager.apply(manager.plan(tool_scenario()))
        assert not applied.success
        history = manager.snapshot.participant_behavior_history
        assert any(
            row.get("invocation_tool_context", {}).get("settlement") == "indeterminate"
            for row in history["participant.behavior.red"]
        )
        # A dispatched peer retains its accepted records even if red is unknown.
        assert "blue observed" in str(list(history["participant.behavior.blue"]))
        with pytest.raises(ConflictError):
            manager.advance_time("time.clock.trial", ticks=1)
        assert len(controllers["red"].effects) == 1
        assert "private-native-canary" not in repr(applied)
