"""Real pinned OpenCode launcher against a local, deterministic provider."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from threading import Event, Thread

import pytest

from aptl.core.opencode import OpenRouterRoute
from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor, OpenCodeOptions
from aptl.workbench.process import AgentExecutionError

pytestmark = pytest.mark.integration


@contextmanager
def provider(*, status=200):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, request))
            self.send_response(status)
            self.send_header(
                "Content-Type",
                "text/event-stream" if status == 200 else "application/json",
            )
            self.end_headers()
            if status != 200:
                self.wfile.write(
                    b'{"error":{"message":"private-test-credential","code":401}}'
                )
                return
            for delta, finish in (
                ({"role": "assistant", "content": "transport completion"}, None),
                ({}, "stop"),
            ):
                chunk = {
                    "id": "gen-fixture",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "test/model",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
                    "usage": {
                        "prompt_tokens": 12,
                        "completion_tokens": 3,
                        "total_tokens": 15,
                    },
                }
                self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/api/v1", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


@pytest.fixture
def opencode_binary():
    selected = os.environ.get("LILRAE_TEST_OPENCODE")
    if not selected:
        pytest.skip("real launcher requires the pinned OpenCode qualification binary")
    return Path(selected).resolve(strict=True)


@pytest.mark.parametrize("status", [200, 401])
@pytest.mark.parametrize("output_limit", [16, 128])
def test_real_launcher_request_and_failure_evidence(
    tmp_path, opencode_binary, status, monkeypatch, output_limit
):
    # Hostile ambient selections must not become the launcher's configuration.
    monkeypatch.setenv("OPENCODE_CONFIG_CONTENT", '{"model":"unapproved/model"}')
    monkeypatch.setenv("ANTHROPIC_API_KEY", "unapproved-credential")
    records = []
    with provider(status=status) as (endpoint, requests):
        active = LilraeOpenCodeExecutor(
            options=OpenCodeOptions(
                executable=opencode_binary,
                work_root=tmp_path,
                environment={"OPENROUTER_API_KEY": "private-test-credential"},
                route=OpenRouterRoute(
                    endpoint=endpoint, serving_provider="test-provider"
                ),
                evidence_sink=records.append,
                max_output_tokens=output_limit,
            ),
            model="openrouter/test/model",
            prompt="Return transport completion.",
            timeout_seconds=90,
        )
        if status == 200:
            assert active("action-transport", Event()) == "transport completion"
        else:
            cancellation = Event()
            with pytest.raises(AgentExecutionError) as error:
                active("action-transport", cancellation)
            assert "private-test-credential" not in str(error.value)
    assert requests
    assert len(requests) == 1
    for path, request in requests:
        assert path == "/api/v1/chat/completions"
        assert request["model"] == "test/model"
        assert request["provider"]["only"] == ["test-provider"]
        assert request["provider"]["allow_fallbacks"] is False
        assert request["max_tokens"] == output_limit
    assert records[0].status == ("succeeded" if status == 200 else "failed")
    assert "private-test-credential" not in repr(records)
    assert not list(tmp_path.glob("lilrae-participant-*"))


def test_real_mcp_child_cannot_inherit_model_credential(tmp_path, opencode_binary):
    from dataclasses import replace
    import sys

    from aptl.backends.participant_tools.session import LilraeToolSession
    from aptl.workbench.lilrae_opencode import OpenCodeToolProfile
    from aptl.workbench.profiles import ProfileId, profile_for
    from tests.test_lilrae_participant_tools import binding, port

    profile = profile_for(ProfileId.RED)
    inventory = {server.server_id: server.tool_names for server in profile.servers}
    report = tmp_path / "child-environment-result"
    child = tmp_path / "mcp.py"
    child.write_text("""import json,os,sys
from pathlib import Path
Path(sys.argv[1]).write_text('isolated' if not os.environ.get('OPENROUTER_API_KEY') else 'leaked')
tools=json.loads(sys.argv[2])
for line in sys.stdin:
    message=json.loads(line)
    if 'id' not in message: continue
    method=message['method']
    if method=='initialize':
        result={'protocolVersion':message['params']['protocolVersion'],'serverInfo':{'name':'fixture','version':'1'},'capabilities':{'tools':{}}}
    elif method=='tools/list':
        result={'tools':[{'name':name,'description':'fixture tool','inputSchema':{'type':'object','properties':{}}} for name in tools]}
    else: result={}
    print(json.dumps({'jsonrpc':'2.0','id':message['id'],'result':result}),flush=True)
""")
    servers = {
        name: {
            "command": sys.executable,
            "args": [str(child), str(report), json.dumps(tools)],
            "env": {},
        }
        for name, tools in inventory.items()
    }
    config = tmp_path / "profile.json"
    config.write_text(json.dumps({"mcpServers": servers}))
    config.chmod(0o600)
    cancellation = Event()
    session = LilraeToolSession(
        port(),
        tuple(
            replace(binding(), server_id=name, tool_name=tool)
            for name, tools in inventory.items()
            for tool in tools
        ),
        cancellation,
    )
    with provider() as (endpoint, requests):
        active = LilraeOpenCodeExecutor(
            options=OpenCodeOptions(
                executable=opencode_binary,
                work_root=tmp_path,
                environment={"OPENROUTER_API_KEY": "private-test-credential"},
                route=OpenRouterRoute(
                    endpoint=endpoint, serving_provider="test-provider"
                ),
                tools=OpenCodeToolProfile(
                    profile=ProfileId.RED,
                    config=config,
                    inventory_probe=lambda name, *args: inventory[name],
                ),
            ),
            model="openrouter/test/model",
            prompt="Return transport completion.",
            timeout_seconds=90,
        )
        assert (
            active.invoke_with_tools("outer-red", cancellation, session)
            == "transport completion"
        )
    assert requests
    assert report.read_text() == "isolated"


@pytest.mark.parametrize("status", [200, 401])
def test_installed_wheel_runs_real_transport_outside_checkout(
    tmp_path, opencode_binary, status
):
    import subprocess
    import sys

    from tests.opencode_fixture import install_wheel

    installed = install_wheel(tmp_path)
    with provider(status=status) as (endpoint, requests):
        project = tmp_path / "independent-project"
        project.mkdir()
        project_config = project / "aptl.json"
        project_config.write_text(
            json.dumps(
                {
                    "lab": {"name": "installed-opencode"},
                    "experiment": {
                        "participant_models": {"opencode": "openrouter/test/model"},
                        "participant_credential_sources": {
                            "opencode": {
                                "kind": "process-environment",
                                "variable": "QUALIFICATION_SOURCE",
                            }
                        },
                    },
                }
            )
        )
        script = """
import hashlib,os,pathlib,sys
from threading import Event
sys.path.insert(0,sys.argv[1])
import aptl.workbench.lilrae_opencode as implementation
assert pathlib.Path(implementation.__file__).resolve().is_relative_to(pathlib.Path(sys.argv[1]).resolve())
from aptl.core.config import AptlConfig
from aptl.core.opencode import OpenRouterRoute
from aptl.backends.lilrae_participant_configuration import opencode_manifest, OpenCodeConfigurationValidator
from aptl.workbench.opencode_bootstrap import OpenCodeParticipantRequest, managed_opencode_executor
from aptl.workbench.process import AgentExecutionError
from raes_contracts.contracts.participant_configuration import ConfigurationOverrideModel, realize_participant_configuration
from raes_contracts.canonical import canonical_contract_digest
project=AptlConfig.model_validate_json(pathlib.Path(sys.argv[5]).read_bytes())
model=project.experiment.participant_models.model_for('opencode')
source=project.experiment.participant_credential_sources.source_for('opencode')
manifest=opencode_manifest(version='1.0.0')
prompt='Return transport completion.'
values={'model':model,'gateway_endpoint':sys.argv[4],'serving_provider':'test-provider',
    'prompt_ref':'content.installed@v1','prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
    'timeout_seconds':90,'max_output_tokens':16}
configuration=realize_participant_configuration(participant_address='participant.behavior.red',
    manifest=manifest,manifest_ref='participant-implementation-manifests.opencode.v1',
    manifest_digest=canonical_contract_digest(manifest),
    overrides=[ConfigurationOverrideModel(target_id=k,value={'kind':'literal','value':v}) for k,v in values.items()],
    validator=OpenCodeConfigurationValidator(frozenset({model})))
with managed_opencode_executor(options=implementation.OpenCodeOptions(
    executable=pathlib.Path(sys.argv[2]),work_root=pathlib.Path(sys.argv[3]),max_output_tokens=16,
    route=OpenRouterRoute(endpoint=sys.argv[4],serving_provider='test-provider')),
    request=OpenCodeParticipantRequest(configuration=configuration,manifest=manifest,prompt=prompt,
        prompt_ref=values['prompt_ref'],supported_models=frozenset({model})),
    run_id='installed-trial',credential_source=source,
    source_environment={source.variable:os.environ[source.variable]}) as (active,evidence):
    if sys.argv[6] == '200':
        assert active('installed-action',Event()) == 'transport completion'
        assert active.last_evidence.status == 'succeeded'
    else:
        try:
            active('installed-action',Event())
        except AgentExecutionError as error:
            assert os.environ[source.variable] not in str(error)
        else:
            raise AssertionError('provider failure was accepted')
        assert active.last_evidence.status == 'failed'
        assert os.environ[source.variable] not in repr(active.last_evidence)
assert evidence.local_cleanup == 'succeeded'
"""
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                script,
                str(installed),
                str(opencode_binary),
                str(tmp_path / "work"),
                endpoint,
                str(project_config),
                str(status),
            ],
            env={**os.environ, "QUALIFICATION_SOURCE": "private-test-credential"},
            cwd=project,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    assert requests


def test_pinned_launchers_execute_both_roles_through_shared_runtime(
    tmp_path, opencode_binary
):
    from dataclasses import replace
    from raes_contracts.contracts.participant_configuration import (
        ConfigurationOverrideModel,
        realize_participant_configuration,
    )
    from raes_contracts.canonical import canonical_contract_digest
    import hashlib

    from aptl.backends.lilrae_participant_configuration import (
        opencode_manifest,
        OpenCodeConfigurationValidator,
        configured_opencode_executor,
    )
    from tests.test_lilrae_concurrent_participants import (
        bindings,
        manager_for,
        scenario,
    )

    records = []
    installed = []
    executors = []
    manifest = opencode_manifest(version="1.0.0")
    with provider() as (endpoint, requests):
        for original in bindings({"red": lambda *args: "", "blue": lambda *args: ""}):
            participant = original.implementation_selection.participant_address
            prompt = f"Return transport completion for {participant}."
            values = {
                "model": "openrouter/test/model",
                "gateway_endpoint": endpoint,
                "serving_provider": "test-provider",
                "max_output_tokens": 128,
                "prompt_ref": "content.prompt@v1",
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "timeout_seconds": 30,
            }
            config = realize_participant_configuration(
                participant_address=participant,
                manifest=manifest,
                manifest_ref=original.implementation_selection.manifest_ref,
                manifest_digest=canonical_contract_digest(manifest),
                overrides=[
                    ConfigurationOverrideModel(
                        target_id=key, value={"kind": "literal", "value": value}
                    )
                    for key, value in values.items()
                ],
                validator=OpenCodeConfigurationValidator(
                    frozenset({"openrouter/test/model"})
                ),
            )
            active = configured_opencode_executor(
                options=OpenCodeOptions(
                    executable=opencode_binary,
                    work_root=tmp_path,
                    environment={"OPENROUTER_API_KEY": "private-test-credential"},
                    route=OpenRouterRoute(
                        endpoint=endpoint, serving_provider="test-provider"
                    ),
                    evidence_sink=records.append,
                ),
                configuration=config,
                manifest=manifest,
                prompt=prompt,
                prompt_ref="content.prompt@v1",
                supported_models=frozenset({"openrouter/test/model"}),
            )
            executors.append(active)
            selection = original.implementation_selection.model_copy(
                update={
                    "implementation_identity": manifest.identity,
                    "manifest_digest": config.manifest_digest,
                    "configuration_ref": "participant-implementation-configurations."
                    + participant.rsplit(".", 1)[1],
                    "configuration_digest": config.configuration_digest,
                }
            )
            installed.append(
                replace(
                    original,
                    implementation_manifest=manifest,
                    implementation_selection=selection,
                    executor=active,
                )
            )
        manager, _ = manager_for(tuple(installed))
        with manager:
            applied = manager.apply(manager.plan(scenario()))
            assert applied.success, applied.diagnostics
            advanced = manager.advance_time("time.clock.trial", ticks=1)
            assert advanced.success, advanced.diagnostics
            history = manager.snapshot.participant_behavior_history
            for role in ("red", "blue"):
                assert "transport completion" in str(
                    list(history[f"participant.behavior.{role}"])
                )
    assert len(records) == 2
    assert all(record.status == "succeeded" for record in records)
    assert len({record.session_id for record in records}) == 2
    assert all(active.last_evidence.build.version == "1.19.5" for active in executors)
    assert len(requests) >= 2
