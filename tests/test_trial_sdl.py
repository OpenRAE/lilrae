"""Trial participants follow the models and prompts that a trial SDL declares (#1670)."""

from __future__ import annotations

import pytest

from aptl.core.trial_sdl import TrialDeclarationError, declared_participants
from aptl.workbench.trial_launch import participant_prompt, participant_tool_servers
from tests.trial_sdl_fixture import ASSET_BYTES, parse_trial, read_fixture_asset, trial_document

_ALL_SERVERS = ("aptl-red", "aptl-indexer", "aptl-network", "aptl-soar", "aptl-threatintel", "aptl-wazuh")
_WITHOUT_INTEL = tuple(name for name in _ALL_SERVERS if name != "aptl-threatintel")


def _prompt(role: str, playbook: str) -> str:
    return (
        ASSET_BYTES[f"{role}-preamble"] + ASSET_BYTES[playbook] + ASSET_BYTES[f"{role}-task"]
    ).decode()


_VARIATIONS = (
    {},
    {"red_model": "openrouter/vendor-c/model-c"},
    {"blue_model": "google-vertex/vendor-d/model-d"},
    {"red_playbook": "red-playbook-loud"},
    {"blue_playbook": "blue-playbook-block"},
    {"intel_present": False},
)


def test_trial_participants_follow_declared_models_prompts_and_misp():
    for variables in _VARIATIONS:
        _check_variation(variables)


def _check_variation(variables):
    document = trial_document(**variables)
    scenario = parse_trial(document)

    participants = {item.role: item for item in declared_participants(scenario)}

    expected = trial_document.__kwdefaults__ | variables
    assert set(participants) == {"red", "blue"}, variables
    assert participants["red"].model == expected["red_model"]
    assert participants["blue"].model == expected["blue_model"]
    assert participant_prompt(scenario, participants["red"], read_fixture_asset) == _prompt(
        "red", expected["red_playbook"]
    )
    assert participant_prompt(scenario, participants["blue"], read_fixture_asset) == _prompt(
        "blue", expected["blue_playbook"]
    )
    selected = _ALL_SERVERS if expected["intel_present"] else _WITHOUT_INTEL
    blue_tools = participant_tool_servers("blue", selected)
    assert ("aptl-threatintel" in blue_tools) is expected["intel_present"]
    assert participant_tool_servers("red", selected) == ("aptl-red",)

    # A changed asset byte is refused, not delivered.
    def tampered(asset):
        return read_fixture_asset(asset) + b"x"

    with pytest.raises(ValueError):
        participant_prompt(scenario, participants["red"], tampered)

    # Two model components on one participant's node is ambiguous.
    ambiguous = trial_document(**variables)
    ambiguous["nodes"]["attacker"]["runtime"]["software_components"].append(
        {"component_id": "second", "name": "second", "model": "openrouter/vendor-x/model-x"}
    )
    with pytest.raises(TrialDeclarationError):
        declared_participants(parse_trial(ambiguous))
