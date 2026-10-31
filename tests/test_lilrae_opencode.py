"""The OpenCode harness receives independent, explicitly selected inputs."""

from aptl.workbench.lilrae_opencode import OpenCodeOptions, OpenCodeToolProfile

import json
import os
from pathlib import Path
from threading import Event

import pytest

from aptl.workbench.process import ProcessResult
from aptl.workbench.process import AgentExecutionError


class RecordingRunner:
    def __init__(self):
        self.calls = []

    def run(self, argv, **options):
        self.calls.append(
            (
                argv,
                options,
                json.loads(Path(options["env"]["OPENCODE_CONFIG"]).read_text()),
            )
        )
        return ProcessResult(0, b'{"type":"text","part":{"text":"done"}}\n', b"")


def test_independent_models_prompts_and_fresh_contexts(tmp_path):
    from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor

    runner = RecordingRunner()
    executable = tmp_path / "opencode"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o700)
    contexts = []
    for model, prompt in (
        ("provider/red", "red only"),
        ("provider/blue", "blue only"),
        ("provider/red", "changed red"),
    ):
        executor = LilraeOpenCodeExecutor(
            options=OpenCodeOptions(
                executable=executable,
                work_root=tmp_path,
                environment={"OPENROUTER_API_KEY": "test-private-token"},
                runner=runner,
            ),
            model=model,
            prompt=prompt,
            timeout_seconds=30,
        )
        assert executor("action-1", Event()) == "done"
        argv, options, config = runner.calls[-1]
        assert options["stdin"] == prompt.encode()
        assert "--model" in argv
        assert model in argv
        assert prompt not in " ".join(argv)
        assert "test-private-token" not in repr(argv)
        assert options["env"]["OPENCODE_DISABLE_PROJECT_CONFIG"] == "true"
        assert options["env"]["OPENCODE_DISABLE_CLAUDE_CODE"] == "true"
        assert config["permission"]["*"] == "deny"
        assert config["share"] == "disabled"
        assert options["env"]["HOME"] != os.environ.get("HOME")
        contexts.append(options["cwd"])
        assert not options["cwd"].exists()
    assert len(set(contexts)) == 3


def test_harness_rejects_ambient_configuration_environment(tmp_path):
    from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor

    options = OpenCodeOptions(
        executable=Path("/bin/true"),
        work_root=tmp_path,
        environment={"OPENCODE_CONFIG": "/untrusted/config"},
    )
    with pytest.raises(ValueError, match="environment"):
        LilraeOpenCodeExecutor(
            options=options,
            model="provider/model",
            prompt="prompt",
            timeout_seconds=30,
        )


def test_only_verified_profile_tools_reach_opencode(tmp_path):
    from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor
    from aptl.workbench.profiles import ProfileId, profile_for

    profile = profile_for(ProfileId.RED)
    servers = {
        server.server_id: {
            "command": "/usr/bin/node",
            "args": ["/admitted/server.js"],
            "env": {},
        }
        for server in profile.servers
    }
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({"mcpServers": servers}))
    path.chmod(0o600)
    inventory = {server.server_id: server.tool_names for server in profile.servers}
    runner = RecordingRunner()
    executor = LilraeOpenCodeExecutor(
        options=OpenCodeOptions(
            executable=Path("/bin/true"),
            work_root=tmp_path,
            environment={},
            runner=runner,
            tools=OpenCodeToolProfile(
                profile=ProfileId.RED,
                config=path,
                credentials={},
                inventory_probe=lambda server, *args: inventory[server],
            ),
        ),
        model="provider/model",
        prompt="red task",
        timeout_seconds=30,
    )
    with pytest.raises(AgentExecutionError, match="tool session"):
        executor("action", Event())
    assert runner.calls == []
    from dataclasses import replace
    from aptl.backends.lilrae_participant_tools import LilraeToolSession
    from tests.test_lilrae_participant_tools import binding, port

    cancellation = Event()
    session = LilraeToolSession(
        port(),
        tuple(
            replace(binding(), server_id=server, tool_name=tool)
            for server, tools in inventory.items()
            for tool in tools
        ),
        cancellation,
    )
    executor.invoke_with_tools("outer-red", cancellation, session)
    config = runner.calls[0][2]
    assert set(config["mcp"]) == set(servers)
    expected = {
        f"{server}_{tool}" for server, tools in inventory.items() for tool in tools
    }
    assert {
        tool for tool, value in config["permission"].items() if value == "allow"
    } == expected
    assert config["permission"]["*"] == "deny"
    for server in config["mcp"].values():
        assert len(server["environment"]["LILRAE_TOOL_TOKEN"]) == 64
        assert not Path(server["environment"]["LILRAE_TOOL_SOCKET"]).exists()
    # Replacing the admitted file cannot widen the next invocation's tools.
    path.write_text(
        json.dumps({"mcpServers": {**servers, "peer": servers[next(iter(servers))]}})
    )
    with pytest.raises(AgentExecutionError, match="changed"):
        executor.invoke_with_tools("outer-red", cancellation, session)
    assert len(runner.calls) == 1


def test_unknown_profile_server_is_rejected_before_probe(tmp_path):
    from unittest.mock import Mock
    from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor
    from aptl.workbench.profiles import ProfileId

    probe = Mock()
    path = tmp_path / "profile.json"
    path.write_text(
        json.dumps(
            {"mcpServers": {"unknown": {"command": "/bin/true", "args": [], "env": {}}}}
        )
    )
    path.chmod(0o600)
    options = OpenCodeOptions(
        executable=Path("/bin/true"),
        work_root=tmp_path,
        tools=OpenCodeToolProfile(
            profile=ProfileId.RED, config=path, inventory_probe=probe
        ),
    )
    with pytest.raises(ValueError, match="servers"):
        LilraeOpenCodeExecutor(
            options=options,
            model="provider/model",
            prompt="task",
            timeout_seconds=30,
        )
    probe.assert_not_called()


def test_real_child_receives_stdin_and_private_configuration(tmp_path):
    import sys
    from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor

    executable = tmp_path / "harness"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json,os,sys\n"
        "assert sys.argv[1:] == ['run','--format','json','--model','provider/model']\n"
        "assert os.environ['HOME'] == os.getcwd()\n"
        "config = json.load(open(os.environ['OPENCODE_CONFIG']))\n"
        "assert config['permission'] == {'*':'deny'}\n"
        "assert sys.stdin.buffer.read() == b'exact prompt'\n"
        "print(json.dumps({'type':'text','part':{'text':'bounded completion'}}))\n"
    )
    executable.chmod(0o700)
    executor = LilraeOpenCodeExecutor(
        options=OpenCodeOptions(
            executable=executable, work_root=tmp_path, environment={}
        ),
        model="provider/model",
        prompt="exact prompt",
        timeout_seconds=15,
    )
    assert executor("action", Event()) == "bounded completion"
    assert not list(tmp_path.glob("lilrae-participant-*"))
