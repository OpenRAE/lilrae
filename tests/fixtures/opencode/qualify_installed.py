"""Pinned OpenCode, installed LilRAE, real RAES and real MCP/IPC transport."""

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
from threading import Event, Thread
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import time
from dataclasses import replace

installed, fixture_root, binary, node, mcp_script, admission, work, mode = sys.argv[1:]
sys.path[:0] = [installed, fixture_root]

from aptl.backends.lilrae_participant_configuration import (
    configured_opencode_executor,
    opencode_manifest,
    OpenCodeConfigurationValidator,
)
from aptl.core.opencode import OpenRouterRoute
import aptl.workbench.lilrae_opencode as executor_module
from aptl.workbench.lilrae_opencode import OpenCodeOptions, OpenCodeToolProfile
from aptl.workbench.process import BoundedProcessRunner
from aptl.backends.participant_tools.transport import LilraeToolTransport
from aptl.workbench.profiles import ProfileId, profile_for
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.participant_configuration import (
    ConfigurationOverrideModel,
    realize_participant_configuration,
)
from raes_contracts.satisfiability import canonical_contract_digest
from tests.lilrae_tool_fixture import tool_scenario, tool_bindings
from tests.test_lilrae_concurrent_participants import manager_for

root = Path(work)
root.mkdir(mode=0o700)
effects = root / "native-effects.jsonl"
shell_effect = root / "shell-effect"
ambient_effect = root / "ambient-effect"
plugin = root / "ambient-plugin.mjs"
plugin.write_text(
    f"import {{writeFileSync}} from 'node:fs'; export const Canary=async()=>{{writeFileSync({json.dumps(str(ambient_effect))},'plugin');return {{}}}};"
)
canary = "ambient-private-history-must-not-reach-model"
(root / "AGENTS.md").write_text(canary)
(root / "opencode.json").write_text(
    json.dumps(
        {
            "plugin": [plugin.as_uri()],
            "permission": {"*": "allow"},
            "mcp": {
                "ambient": {
                    "type": "local",
                    "command": [
                        sys.executable,
                        "-c",
                        f"from pathlib import Path; Path({str(ambient_effect)!r}).write_text('mcp')",
                    ],
                }
            },
        }
    )
)
host_home = root / "host-home"
(host_home / ".config/opencode").mkdir(parents=True)
(host_home / ".config/opencode/opencode.json").write_text(
    (root / "opencode.json").read_text()
)
(host_home / ".local/share/opencode").mkdir(parents=True)
(host_home / ".local/share/opencode/auth.json").write_text(
    json.dumps({"openrouter": {"type": "api", "key": canary}})
)
(host_home / ".local/share/opencode/history.json").write_text(
    json.dumps({"messages": [canary]})
)
os.environ["HOME"] = str(host_home)
os.environ["OPENCODE_CONFIG"] = str(root / "opencode.json")

requests = []
violations = []
release_response = Event()
responses_started = Event()
FAILURE_MODES = {
    "timeout",
    "cancel",
    "malformed",
    "teardown",
    "invalid-terminal",
    "transport-teardown",
    "transport-timeout",
    "teardown-timeout",
    "teardown-cancel",
}


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert self.headers["Authorization"] == "Bearer private-test-credential"
        assert payload["model"] == "test/model"
        assert canary not in json.dumps(payload)
        role = (
            "red"
            if "qualification-role-red" in json.dumps(payload["messages"])
            else "blue"
        )
        requests.append((role, payload))
        tools = payload.get("tools", [])
        if any(row["function"]["name"] == "bash" for row in tools):
            violations.append("built-in shell was offered")
        if any(row["role"] == "tool" for row in payload["messages"]):
            delta, finish = (
                {"role": "assistant", "content": "qualification completed"},
                "stop",
            )
        else:
            suffix = "kali_run_command" if role == "red" else "wazuh_query_alerts"
            selected = next(
                row["function"]["name"]
                for row in tools
                if row["function"]["name"].endswith(suffix)
            )
            args = (
                {"command": "id"}
                if role == "red"
                else {"endpoint": "/agents", "method": "GET"}
            )
            if mode == "forbidden-arguments":
                args = (
                    {"command": "not-admitted"}
                    if role == "red"
                    else {"endpoint": "/not-admitted", "method": "GET"}
                )
            if mode == "builtin-shell":
                selected = "bash"
                args = {
                    "command": f"echo escaped > {shell_effect}",
                    "description": "qualification denial",
                }
            delta = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": f"call_{role}",
                        "type": "function",
                        "function": {"name": selected, "arguments": json.dumps(args)},
                    }
                ],
            }
            finish = "tool_calls"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        if mode == "malformed":
            self.wfile.write(b"data: {invalid-json}\n\ndata: [DONE]\n\n")
            self.wfile.flush()
            return
        if mode in {
            "timeout",
            "cancel",
            "transport-timeout",
            "teardown-timeout",
            "teardown-cancel",
        }:
            chunk = {
                "id": "partial",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "test/model",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": "partial"},
                        "finish_reason": None,
                    }
                ],
            }
            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
            self.wfile.flush()
            if len({role for role, _ in requests}) == 2:
                responses_started.set()
            release_response.wait(40)
            return
        for part, reason in ((delta, None), ({}, finish)):
            chunk = {
                "id": "gen-fixture",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "test/model",
                "choices": [{"index": 0, "delta": part, "finish_reason": reason}],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 3,
                    "total_tokens": 15,
                },
            }
            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
thread = Thread(target=server.serve_forever, daemon=True)
thread.start()
endpoint = f"http://127.0.0.1:{server.server_port}/api/v1"
manifest = opencode_manifest(version="1.0.0")
records = []
bindings = []


class Placeholder:
    def __call__(self, *args):
        raise AssertionError("unconfigured executor")

    def invoke_with_tools(self, *args):
        raise AssertionError("unconfigured executor")


class TerminalFaultRunner:
    """Corrupt the real launcher's terminal sequence after supervised cleanup."""

    def run(self, argv, **kwargs):
        result = BoundedProcessRunner().run(argv, **kwargs)
        events = [
            json.loads(line) for line in result.stdout.splitlines() if line.strip()
        ]
        index = next(
            i
            for i, event in enumerate(events)
            if event.get("type") == "step_finish" and event["part"]["reason"] == "stop"
        )
        failure = dict(events[index])
        failure["part"] = {**failure["part"], "reason": "error"}
        events.insert(index, failure)
        return replace(
            result, stdout=b"\n".join(json.dumps(row).encode() for row in events)
        )


def verify_evidence(mode, records):
    if mode in FAILURE_MODES:
        assert all(record.status == "failed" for record in records), records
        assert all(record.session_id for record in records), records
        assert all(record.stdout_bytes > 0 for record in records), records
        assert all(record.stdout_sha256 for record in records), records
        assert all(record.cleanup_residual == () for record in records), records
    if mode == "invalid-terminal":
        assert all(record.finish_reason == "error" for record in records), records
        assert all(record.partial_text_sha256 for record in records), records
        assert all(record.input_tokens > 0 for record in records), records
    if mode in {"transport-teardown", "transport-timeout"}:
        assert all(
            record.tool_transport_cleanup == "uncertain" for record in records
        ), records
        if mode == "transport-teardown":
            assert all(record.partial_text_sha256 for record in records), records
        assert all(record.stdout_sha256 for record in records), records
        assert all(record.cleanup_residual == () for record in records), records
        assert "private-test-credential" not in repr(records)
    else:
        assert all(
            record.tool_transport_cleanup == "succeeded" for record in records
        ), records


def run_trial(selected_mode):
    global mode
    mode = selected_mode
    requests.clear()
    violations.clear()
    responses_started.clear()
    release_response.clear()
    effects.unlink(missing_ok=True)
    bindings = []
    records = []
    for original in tool_bindings({"red": Placeholder(), "blue": Placeholder()}):
        participant = original.implementation_selection.participant_address
        role = participant.rsplit(".", 1)[1]
        profile_id = ProfileId.RED if role == "red" else ProfileId.GUIDED_BLUE
        profile = profile_for(profile_id)
        servers, inventory, mapped = {}, {}, []
        for declared in profile.servers:
            configuration = {"server": declared.server_id, "participant": participant}
            inventory[declared.server_id] = declared.tool_names
            servers[declared.server_id] = {
                "command": node,
                "args": [
                    mcp_script,
                    admission,
                    json.dumps(declared.tool_names),
                    json.dumps(configuration),
                    str(effects),
                ],
                "env": {"APTL_MCP_DISABLE_DOTENV": "1", "OTEL_SDK_DISABLED": "true"},
            }
            for name in declared.tool_names:
                selected = "kali_run_command" if role == "red" else "wazuh_query_alerts"
                expected = (
                    {"command": "id"}
                    if role == "red"
                    else {"endpoint": "/agents", "method": "GET"}
                )
                mapped.append(
                    replace(
                        original.tool_bindings[0],
                        server_id=declared.server_id,
                        tool_name=name,
                        configuration_digest=canonical_json_digest(configuration),
                        accepts_arguments=lambda args, allowed=name == selected, expected=expected: (
                            allowed and args == expected
                        ),
                    )
                )
        client_config = root / f"{role}-mcp.json"
        client_config.write_text(json.dumps({"mcpServers": servers}))
        client_config.chmod(0o600)
        prompt = (
            f"qualification-role-{role}: invoke the admitted observation tool once."
        )
        values = {
            "model": "openrouter/test/model",
            "gateway_endpoint": endpoint,
            "serving_provider": "test-provider",
            "prompt_ref": "content.qualification@v1",
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "timeout_seconds": 5
            if mode in {"timeout", "malformed", "transport-timeout", "teardown-timeout"}
            else 30,
            "max_output_tokens": 128,
        }
        configuration = realize_participant_configuration(
            participant_address=participant,
            manifest=manifest,
            manifest_ref=original.implementation_selection.manifest_ref,
            manifest_digest=canonical_contract_digest(manifest),
            overrides=[
                ConfigurationOverrideModel(
                    target_id=k, value={"kind": "literal", "value": v}
                )
                for k, v in values.items()
            ],
            validator=OpenCodeConfigurationValidator(frozenset({values["model"]})),
        )
        active = configured_opencode_executor(
            options=OpenCodeOptions(
                executable=Path(binary),
                work_root=root,
                environment={"OPENROUTER_API_KEY": "private-test-credential"},
                route=OpenRouterRoute(
                    endpoint=endpoint, serving_provider="test-provider"
                ),
                evidence_sink=records.append,
                runner=TerminalFaultRunner() if mode == "invalid-terminal" else None,
                tools=OpenCodeToolProfile(profile=profile_id, config=client_config),
            ),
            configuration=configuration,
            manifest=manifest,
            prompt=prompt,
            prompt_ref=values["prompt_ref"],
            supported_models=frozenset({values["model"]}),
        )
        selection = original.implementation_selection.model_copy(
            update={
                "implementation_identity": manifest.identity,
                "manifest_digest": configuration.manifest_digest,
                "configuration_ref": f"participant-implementation-configurations.{role}",
                "configuration_digest": configuration.configuration_digest,
            }
        )
        bindings.append(
            replace(
                original,
                implementation_manifest=manifest,
                implementation_selection=selection,
                executor=active,
                tool_bindings=tuple(mapped),
            )
        )
    manager, runtime = manager_for(tuple(bindings))
    with manager:
        plan = manager.plan(tool_scenario())
        if mode in {"cancel", "teardown-cancel"}:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(manager.apply, plan)
                assert responses_started.wait(20), "invocations did not reach provider"
                time.sleep(0.5)
                runtime.autonomous_execution.cancel()
                result = pending.result(timeout=40)
        else:
            result = manager.apply(plan)
        if mode in {
            "teardown",
            "transport-teardown",
            "transport-timeout",
            "teardown-timeout",
            "teardown-cancel",
        }:
            assert not result.success
            assert any(
                item.code == "runtime.control-plane.operation-indeterminate"
                for item in result.diagnostics
            ), result.diagnostics
        else:
            assert result.success, result.diagnostics
        if mode == "authorized":
            for role in ("red", "blue"):
                history = list(
                    manager.snapshot.participant_behavior_history[
                        f"participant.behavior.{role}"
                    ]
                )
                assert len(history) == 6, history
                assert all(row.get("invocation_tool_context") for row in history[:3]), (
                    history
                )
                assert "qualification completed" in str(history), history
    native = (
        [json.loads(row) for row in effects.read_text().splitlines()]
        if effects.exists()
        else []
    )
    assert len(native) == (
        2
        if mode in {"authorized", "teardown", "invalid-terminal", "transport-teardown"}
        else 0
    ), native
    if mode == "authorized":
        assert {row["server"] for row in native} == {"aptl-red", "aptl-wazuh"}
        assert all(record.status == "succeeded" for record in records), records
    assert not shell_effect.exists()
    assert not ambient_effect.exists()
    assert len(records) == 2
    assert not violations, violations
    assert {role for role, _ in requests} == {"red", "blue"}
    assert not list(root.glob("lilrae-participant-*"))
    for name, module in tuple(sys.modules.items()):
        if name.startswith("aptl") and getattr(module, "__file__", None):
            assert (
                Path(module.__file__)
                .resolve()
                .is_relative_to(Path(installed).resolve())
            ), module.__file__
    verify_evidence(mode, records)
    observed = {record.session_id for record in records if record.session_id}
    for item in bindings:
        item.executor.close()
    return {
        "mode": mode,
        "native_effects": len(native),
        "roles": 2,
        "isolated": True,
    }, observed


requested_mode = mode
actual_directory = executor_module.TemporaryDirectory
actual_transport_exit = LilraeToolTransport.__exit__


def fail_transport_exit(self, *args):
    actual_transport_exit(self, *args)
    raise RuntimeError("private-test-credential")


@contextmanager
def fail_teardown(**kwargs):
    try:
        with actual_directory(**kwargs) as directory:
            yield directory
    finally:
        raise OSError("private-test-credential")


try:
    if requested_mode in {"teardown", "teardown-timeout", "teardown-cancel"}:
        executor_module.TemporaryDirectory = fail_teardown
    if requested_mode in {"transport-teardown", "transport-timeout"}:
        LilraeToolTransport.__exit__ = fail_transport_exit
    try:
        summary, previous_sessions = run_trial(requested_mode)
    finally:
        executor_module.TemporaryDirectory = actual_directory
        LilraeToolTransport.__exit__ = actual_transport_exit
        release_response.set()
    if requested_mode in FAILURE_MODES:
        following, next_sessions = run_trial("authorized")
        assert following["native_effects"] == 2
        assert not previous_sessions.intersection(next_sessions)
        summary["clean_next_trial"] = True
    print(json.dumps(summary))
finally:
    release_response.set()
    server.shutdown()
    server.server_close()
    thread.join(timeout=10)
