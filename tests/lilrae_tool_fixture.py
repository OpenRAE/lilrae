"""Authored tool relations and exact installed native offers for integration."""

from dataclasses import replace

from raes.participant_behavior_specification import ParticipantToolAffordance
from raes_contracts.canonical import canonical_json_digest
from raes_processor.compiler import compile_runtime_model

from tests.lilrae_concurrent_fixture import scenario
from tests.test_lilrae_concurrent_participants import bindings
from tests.test_lilrae_participant_tools import binding


def tool_scenario():
    authored = scenario()
    authored.action_contracts["native"] = authored.action_contracts["red"].model_copy(
        deep=True
    )
    behavior = authored.behavior_specifications["duel"]
    behavior.action_contract_refs.append("native")
    for agent in authored.agents.values():
        agent.actions.append("native")
    behavior.tool_affordances["native"] = ParticipantToolAffordance(
        action_contract_refs=["native"], observation_boundary_refs=["red"]
    )
    boundary = authored.observation_boundaries["red"]
    ref = "behavior_specifications.duel.tool_affordances.native"
    boundary.observable_refs.append(ref)
    authored.observation_boundaries["red"] = type(boundary).model_validate(
        boundary.model_dump()
        | {
            "view_rules": [
                {
                    "information_ref": ref,
                    "boundary_class": "observable_resource",
                    "disposition": "observable",
                    "visibility_basis": "Authored participant tool",
                }
            ]
        }
    )
    return authored


def tool_bindings(executors, authored=None):
    model = compile_runtime_model(authored or tool_scenario())
    digest = canonical_json_digest(
        model.action_contracts["participant.action-contract.native"].spec
    )
    installed = []
    for item in bindings(executors):
        role = item.implementation_selection.participant_address.rsplit(".", 1)[-1]
        tool = binding(
            server="aptl-red" if role == "red" else "aptl-wazuh",
            tool="kali_run_command" if role == "red" else "wazuh_api_request",
            matcher=lambda args: (
                args in ({"command": "id"}, {"endpoint": "/agents", "method": "GET"})
            ),
        )
        installed.append(
            replace(item, tool_bindings=(replace(tool, action_contract_digest=digest),))
        )
    return tuple(installed)
