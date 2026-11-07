"""Trial participants follow the models and prompts that a trial SDL declares (#1670)."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import pytest

from aptl.core.config import ExperimentSettings
from aptl.core.mcp_policy import McpPolicy, select_scenario_servers
from aptl.core.opencode import OpenCodeBuild
from aptl.core.trial_sdl import TrialDeclarationError, declared_participants
from aptl.workbench.process import ProcessResult
from aptl.workbench.trial_launch import TrialLaunchSettings, trial_executors
from tests.trial_sdl_fixture import (
    ASSET_BYTES,
    catalog_inventory,
    mcp_document,
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
_PROVIDERS = {
    "openrouter/vendor-a/model-a": "vendor-a",
    "openrouter/vendor-b/model-b": "vendor-b",
    "openrouter/vendor-c/model-c": "vendor-c",
    "openrouter/vendor-d/model-d": "vendor-d",
}


class LaunchRecorder:
    """Record each child's model, standard input and rendered tool config."""

    def __init__(self):
        self.calls = []

    def run(self, argv, **options):
        config = json.loads(Path(options["env"]["OPENCODE_CONFIG"]).read_text())
        self.calls.append({"argv": argv, "stdin": options["stdin"], "config": config})
        return ProcessResult(
            0,
            b'{"type":"text","part":{"text":"done"}}\n{"type":"step_finish","part":{"reason":"stop"}}\n',
            b"",
        )


def _prompt(role: str, playbook: str) -> bytes:
    return ASSET_BYTES[f"{role}-preamble"] + ASSET_BYTES[playbook] + ASSET_BYTES[f"{role}-task"]


def _settings(tmp_path, scenario, runner):
    executable = tmp_path / "opencode"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o700)
    work = tmp_path / "work"
    work.mkdir(mode=0o700)
    mcp_config = tmp_path / ".mcp.json"
    mcp_config.write_text(json.dumps(mcp_document(sys.executable)))
    mcp_config.chmod(0o600)
    return TrialLaunchSettings(
        executable=executable,
        work_root=work,
        experiment=ExperimentSettings.model_validate(
            {
                "participant_credential_sources": {
                    "opencode": {"kind": "process-environment", "variable": "TEST_ROUTER_KEY"}
                },
                "participant_serving_providers": _PROVIDERS,
            }
        ),
        source_environment={"TEST_ROUTER_KEY": "synthetic-router-key"},
        mcp_config=mcp_config,
        server_ids=select_scenario_servers(scenario, McpPolicy()),
        build=OpenCodeBuild(
            version="1.19.5",
            executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        ),
        runner=runner,
        inventory_probe=catalog_inventory,
    )


def test_trial_participants_follow_declared_models_prompts_and_misp(tmp_path):
    for index, variables in enumerate(_VARIATIONS):
        _check_variation(tmp_path / str(index), variables)


def _check_variation(tmp_path, variables):
    tmp_path.mkdir(mode=0o700)
    expected = trial_document.__kwdefaults__ | variables
    scenario = parse_trial(trial_document(**variables))
    participants = declared_participants(scenario)
    roles = {item.role: item for item in participants}
    assert set(roles) == {"red", "blue"}, variables

    runner = LaunchRecorder()
    with trial_executors(
        scenario,
        participants,
        run_id="run-1",
        deadline=datetime.now(UTC) + timedelta(minutes=5),
        settings=_settings(tmp_path, scenario, runner),
        read_asset=read_fixture_asset,
        evidence_sink=lambda address, item: None,
    ) as executors:
        for role in ("red", "blue"):
            executors[roles[role].address]("action-1", Event())

    red, blue = runner.calls
    assert expected["red_model"] in red["argv"]
    assert expected["blue_model"] in blue["argv"]
    assert red["stdin"] == _prompt("red", expected["red_playbook"])
    assert blue["stdin"] == _prompt("blue", expected["blue_playbook"])
    assert set(red["config"]["mcp"]) == {"aptl-red"}
    assert ("aptl-threatintel" in blue["config"]["mcp"]) is expected["intel_present"]
    assert red["config"]["permission"]["*"] == "deny"
    assert not any(name.startswith("aptl-threatintel") for name in red["config"]["permission"])

    # A changed asset byte is refused before any participant starts.
    def tampered(asset):
        return read_fixture_asset(asset) + b"x"

    (tmp_path / "tampered").mkdir(mode=0o700)
    refused = trial_executors(
        scenario,
        participants,
        run_id="run-2",
        deadline=datetime.now(UTC) + timedelta(minutes=5),
        settings=_settings(tmp_path / "tampered", scenario, LaunchRecorder()),
        read_asset=tampered,
        evidence_sink=lambda address, item: None,
    )
    with pytest.raises(ValueError):
        refused.__enter__()

    # Two model components on one participant's node is ambiguous.
    ambiguous = trial_document(**variables)
    ambiguous["nodes"]["kali"]["runtime"]["software_components"].append(
        {"component_id": "second", "name": "second", "model": "openrouter/vendor-x/model-x"}
    )
    ambiguous_scenario = parse_trial(ambiguous)
    with pytest.raises(TrialDeclarationError):
        declared_participants(ambiguous_scenario)
