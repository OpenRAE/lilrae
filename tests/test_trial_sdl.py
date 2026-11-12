"""Trial participants follow the models and prompts that a trial SDL declares (#1670)."""

from __future__ import annotations


import pytest

from aptl.core.mcp_policy import McpPolicy, select_scenario_servers
from aptl.core.trial_sdl import TrialDeclarationError, declared_participants
from tests.trial_sdl_fixture import (
    ASSET_BYTES,
    parse_trial,
    read_fixture_asset,
    trial_document,
)

_VARIATIONS = (
    {},
    {"red_model": "openrouter/vendor-c/model-c"},
    {"blue_model": "openrouter/vendor-d/model-d"},
    {"red_playbook": "red-playbook-loud"},
    {"blue_playbook": "blue-playbook-block"},
    {"intel_present": False},
)


def test_trial_participants_follow_declared_models_prompts_and_misp():
    from aptl.workbench.trial_launch import participant_prompt, participant_tool_servers

    for variables in _VARIATIONS:
        expected = trial_document.__kwdefaults__ | variables
        scenario = parse_trial(trial_document(**variables))
        roles = {item.role: item for item in declared_participants(scenario)}
        assert set(roles) == {"red", "blue"}
        servers = select_scenario_servers(scenario, McpPolicy())
        for role in ("red", "blue"):
            assert roles[role].model == expected[f"{role}_model"]
            prompt = participant_prompt(scenario, roles[role], read_fixture_asset)
            assert prompt.encode() == (
                ASSET_BYTES[f"{role}-preamble"]
                + ASSET_BYTES[expected[f"{role}_playbook"]]
                + ASSET_BYTES[f"{role}-task"]
            )
        assert participant_tool_servers("red", servers) == ("aptl-red",)
        assert ("aptl-threatintel" in participant_tool_servers("blue", servers)) is expected["intel_present"]
        with pytest.raises(ValueError):
            participant_prompt(scenario, roles["red"], lambda asset: read_fixture_asset(asset) + b"x")


def test_admitted_configurations_select_the_model_and_prompts():
    from types import SimpleNamespace

    from aptl.core.trial_sdl import TrialDeclarationError, admitted_participants

    scenario = parse_trial(trial_document())

    def value(target, literal, declaration=None):
        selection = SimpleNamespace(declaration_ref=declaration) if declaration else None
        return SimpleNamespace(target_id=target, value=SimpleNamespace(value=literal), control_context_selection=selection)

    configuration = SimpleNamespace(
        participant_address="agents.red-operator",
        configuration=SimpleNamespace(values=[
            value("context.preamble", "control_context_assets.red-preamble", "control_context_assets.red-preamble"),
            value("context.task", "control_context_assets.red-task", "control_context_assets.red-task"),
            value("model", "google-vertex/zai-org/glm-5.2-maas"),
        ]),
    )
    (participant,) = admitted_participants(scenario, (configuration,))
    assert (participant.agent, participant.role, participant.model, participant.context_assets) == (
        "red-operator", "red", "google-vertex/zai-org/glm-5.2-maas", ("red-preamble", "red-task"))
    stranger = SimpleNamespace(participant_address="agents.absent", configuration=configuration.configuration)
    with pytest.raises(TrialDeclarationError):
        admitted_participants(scenario, (stranger,))
