"""Qualify the released port's refusal boundaries without adding backend semantics."""

from dataclasses import replace
from threading import Event
from unittest.mock import Mock

import pytest
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.participant_tool_actions import ParticipantToolActionRefusal
from raes_processor.compiler import compile_runtime_model
from raes_runtime.participant_invocation_tool_actions import (
    InvocationToolActionConfiguration,
    ParticipantInvocationToolActions,
)

from aptl.backends.raes_manifest import create_aptl_manifest
from aptl.backends.lilrae_participant_tools import LilraeToolSession
from aptl.workbench.process import AgentExecutionError
from tests.lilrae_tool_fixture import tool_bindings, tool_scenario
from tests.test_lilrae_tool_runtime import Controller


@pytest.mark.parametrize(
    "composition, expected",
    [
        ("resource", ParticipantToolActionRefusal.RESOURCE_GOVERNANCE_UNSUPPORTED),
        ("crossing", ParticipantToolActionRefusal.CROSSING_MEDIATION_UNSUPPORTED),
        ("shared-time", ParticipantToolActionRefusal.TEMPORAL_BINDING_UNSUPPORTED),
    ],
)
def test_released_composition_refuses_before_native_effects(composition, expected):
    installed = tool_bindings({"red": Controller("red")})
    item = installed[0]
    model = compile_runtime_model(tool_scenario())
    policy = model.behavior_specifications[
        "participant.behavior-specification.duel"
    ].autonomous_execution
    if composition == "resource":
        policy = replace(policy, profile="participant-autonomous-execution/v3")
    if composition == "shared-time":
        policy = replace(
            policy,
            invocation_tool_bindings=tuple(
                replace(binding, shared_time_bound=True)
                for binding in policy.invocation_tool_bindings
            ),
        )
    ledger = Mock()
    configuration = InvocationToolActionConfiguration.from_manifest(
        create_aptl_manifest(autonomous_bindings=installed).participant_runtime,
        ledger=ledger,
        crossing_installed=composition == "crossing",
    )
    outer = ParticipantActionAdmissionRequest(
        participant_address=item.implementation_selection.participant_address,
        action_contract_address=item.execution_binding.action_contract_address,
        observation_boundary_address=item.observation_boundary_address,
        action_instance_id="outer",
        implementation_manifest=item.implementation_manifest,
        implementation_selection=item.implementation_selection,
        requires_terminal_outcome=True,
        target_addresses=item.execution_binding.target_addresses,
        execution_scope_ref="scope:trial",
        execution_generation=0,
    )
    port = ParticipantInvocationToolActions(
        outer=outer,
        episode_id="episode",
        policy=policy,
        configuration=configuration,
        scheduler_state_key="state:trial",
        prior_history_length=0,
    )
    port.activate()
    observed = []
    # Retain the real typed decision while exercising the consumer's refusal.
    original = port.admit

    def record(request):
        decision = original(request)
        observed.append(decision)
        return decision

    port.admit = record
    native = Mock()
    try:
        with pytest.raises(AgentExecutionError):
            LilraeToolSession(port, item.tool_bindings, Event()).invoke(
                "aptl-red",
                "kali_run_command",
                {"command": "id"},
                "call",
                native,
            )
        assert observed[0].refusal is expected
        native.assert_not_called()
        assert not ledger.mock_calls
    finally:
        assert port.close() == ()
