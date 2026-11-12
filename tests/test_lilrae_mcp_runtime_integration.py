"""Real RAES, Python IPC, Node MCP handlers and SDK on the same call path.

Native SSH/API operations use deterministic substitutes. This does not claim
installed-lab qualification or make an external model/service request.
"""

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from raes_contracts.canonical import canonical_json_digest

from aptl.backends.participant_tools.transport import LilraeToolTransport
from tests.lilrae_tool_fixture import tool_scenario, tool_bindings
from tests.test_lilrae_tool_runtime import Controller
from tests.test_lilrae_concurrent_participants import manager_for

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "mcp/aptl-mcp-common/tests/fixtures/lilrae-runtime-client.mjs"


def configuration(role):
    config = {
        "server": {
            "name": "lilrae-integration-" + role,
            "version": "1.0.0",
            "description": "Integration fixture",
            "toolPrefix": "kali" if role == "red" else "wazuh",
            "targetName": "Declared target",
            "configKey": "target",
            "envPrefix": "LILRAE_TEST",
        },
        "lab": {"name": "fixture", "network_subnet": "172.20.0.0/16"},
    }
    if role == "red":
        config["containers"] = {
            "target": {
                "container_name": "fixture",
                "container_ip": "localhost",
                "ssh_key": "/unused/fixture-key",
                "ssh_user": "fixture",
                "ssh_port": 22,
                "enabled": True,
            }
        }
    else:
        config["api"] = {
            "baseUrl": "https://fixture.invalid:55000",
            "auth": {"type": "none"},
        }
    return config


@pytest.mark.integration
def test_both_mcp_handlers_execute_under_actual_runtime_authority():
    node = shutil.which("node")
    assert node, "the MCP integration gate requires Node"
    assert (ROOT / "mcp/aptl-mcp-common/build/server.js").is_file(), (
        "build common MCP before this gate"
    )

    class NativeController(Controller):
        def invoke_with_tools(self, action, cancellation, tools):
            with LilraeToolTransport(tools) as carrier:
                execution = subprocess.run(
                    [node, str(SCRIPT), self.role],
                    env={
                        "PATH": os.defpath,
                        **carrier.environment(
                            "aptl-red" if self.role == "red" else "aptl-wazuh"
                        ),
                        "LILRAE_TEST_CONFIGURATION": json.dumps(
                            configuration(self.role)
                        ),
                        "OTEL_SDK_DISABLED": "true",
                    },
                    capture_output=True,
                    timeout=30,
                    check=True,
                )
                reply = json.loads(execution.stdout)
                assert not reply.get("isError"), reply
                payload = json.loads(reply["content"][0]["text"])
                assert payload["success"] is True
                count = (
                    json.loads(payload["output"]["stdout"])["effects"]
                    if self.role == "red"
                    else payload["data"]["effects"]
                )
                assert count == 1
                self.effects.append(payload)
            return self.role + " native tool observed"

    controllers = {role: NativeController(role) for role in ("red", "blue")}
    installed = []
    for item in tool_bindings(controllers):
        role = item.implementation_selection.participant_address.rsplit(".", 1)[-1]
        tool = replace(
            item.tool_bindings[0],
            tool_name="kali_run_command" if role == "red" else "wazuh_api_call",
            configuration_digest=canonical_json_digest(configuration(role)),
        )
        installed.append(replace(item, tool_bindings=(tool,)))
    manager, _ = manager_for(tuple(installed))
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
