"""Real installed CLI controls against local APIs, without model-service access."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from pathlib import Path
import json
import os
import subprocess
import sys
import re
import hashlib

import pytest

from tests.opencode_fixture import install_wheel
from tests.test_participant_request_dispatch import prepared_request

QUALIFIED_BUILDS = {
    "claude": (
        "2.1.316",
        "fd13c70000fec3f2116dfbcbb6121210b4a29328bf0e46210a59dd594a67d824",
    ),
    "codex": (
        "0.166.0",
        "b8a11fedf24b2dfb59a70c9e52b030f9a508dcd49cd2dd0d41956f4c785156b8",
    ),
}


@contextmanager
def native_api(provider, model, status):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"data": [{"id": model}]}).encode())

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, body))
            if status != 200:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    b'{"error":{"type":"authentication_error","message":"fixture rejected"}}'
                )
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            if provider == "claude":
                text = '{"candidate":0}'
                message = {
                    "id": "msg_fixture",
                    "type": "message",
                    "role": "assistant",
                    "model": model,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 12, "output_tokens": 0},
                }
                events = [
                    ("message_start", {"type": "message_start", "message": message}),
                    (
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": 0,
                            "content_block": {"type": "text", "text": ""},
                        },
                    ),
                    (
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": 0,
                            "delta": {"type": "text_delta", "text": text},
                        },
                    ),
                    ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                    (
                        "message_delta",
                        {
                            "type": "message_delta",
                            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                            "usage": {"output_tokens": 4},
                        },
                    ),
                    ("message_stop", {"type": "message_stop"}),
                ]
            else:
                item = {
                    "id": "msg_fixture",
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"candidate":0}',
                            "annotations": [],
                        }
                    ],
                }
                response = {
                    "id": "resp_fixture",
                    "object": "response",
                    "status": "completed",
                    "model": model,
                    "output": [item],
                    "usage": {
                        "input_tokens": 12,
                        "output_tokens": 4,
                        "total_tokens": 16,
                        "input_tokens_details": {"cached_tokens": 0},
                        "output_tokens_details": {"reasoning_tokens": 0},
                    },
                }
                events = [
                    (
                        "response.output_item.done",
                        {
                            "type": "response.output_item.done",
                            "output_index": 0,
                            "item": item,
                        },
                    ),
                    (
                        "response.completed",
                        {"type": "response.completed", "response": response},
                    ),
                ]
            for name, data in events:
                self.wfile.write(
                    f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()
                )
            self.wfile.flush()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield (
            f"http://127.0.0.1:{server.server_port}"
            + ("" if provider == "claude" else "/v1"),
            requests,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


@pytest.mark.integration
@pytest.mark.parametrize(
    "provider,model,status,mode,effort",
    [
        ("claude", "claude-sonnet-5-5", 200, "effort", effort)
        for effort in ("low", "medium", "high", "xhigh", "max")
    ]
    + [
        ("codex", "gpt-5.2-codex", 200, "effort", effort)
        for effort in ("none", "minimal", "low", "medium", "high", "xhigh")
    ]
    + [
        ("claude", "claude-sonnet-5-5", 401, "effort", "high"),
        ("codex", "gpt-5.2-codex", 401, "effort", "high"),
        ("codex", "gpt-5.2-codex", 200, "disabled", None),
    ],
)
def test_installed_cli_applies_reasoning_no_fallback_and_exact_context(
    tmp_path, provider, model, status, mode, effort
):
    selected = os.environ.get(f"LILRAE_TEST_{provider.upper()}")
    if not selected:
        pytest.skip("native CLI qualification requires its explicitly selected binary")
    executable = Path(selected).resolve(strict=True)
    expected_version, expected_sha256 = QUALIFIED_BUILDS[provider]
    assert hashlib.sha256(executable.read_bytes()).hexdigest() == expected_sha256
    installed = install_wheel(tmp_path)
    version_output = subprocess.run(
        [str(executable), "--version"],
        env={"PATH": os.defpath},
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout
    build_version = re.search(r"\d+\.\d+\.\d+", version_output).group()
    assert build_version == expected_version
    with native_api(provider, model, status) as (endpoint, requests):
        request, owner, scenario = prepared_request(
            provider,
            executable,
            endpoint=endpoint,
            model=model,
            build_version=build_version,
            reasoning_mode=mode,
            reasoning_effort=effort,
            with_owner=True,
        )
        data = {
            **request.__dict__,
            "profile": request.profile.model_dump(mode="json"),
            "trusted": {
                "catalog": owner.catalog.model_dump(mode="json"),
                "scenario": scenario.model_dump(mode="json"),
            },
        }
        script = """
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from aptl.core.participant_requests import ParticipantRequest,RequestProfile,ParticipantRequestBinding,ParticipantRequestOwner,RequestCatalog
from raes import Scenario
from raes_contracts.participant_control_context import control_context_asset_reference
from aptl.workbench.runtime import DecisionAgentLaunch
from aptl.workbench.agent import ClaudeCodeManagedAgentAdapter
from aptl.workbench.codex_agent import CodexManagedAgentAdapter
from aptl.workbench.process import AgentExecutionError
from aptl.core.runstore import LocalRunStore
data=json.loads(sys.stdin.read())
trusted=data.pop('trusted')
scenario=Scenario.model_validate(trusted['scenario'])
owner=ParticipantRequestOwner(catalog=RequestCatalog.model_validate_json(json.dumps(trusted['catalog'])),scenario=scenario,context_domains={'brief':{'control_context_assets.brief-terse':control_context_asset_reference(scenario.control_context_assets['brief-terse'])}})
data['profile']=RequestProfile.model_validate_json(json.dumps(data['profile']))
request=ParticipantRequest(**data)
provider=request.provider
factory=ClaudeCodeManagedAgentAdapter if provider=='claude' else CodexManagedAgentAdapter
kwargs={('claude_executable' if provider=='claude' else 'codex_executable'):Path(sys.argv[2])}
store=LocalRunStore(Path(sys.argv[3])/'runs')
adapter=factory(**kwargs,work_dir=Path(sys.argv[3])/'native',timeout_seconds=120 if sys.argv[4]=='200' else 20,run_store=store)
key='ANTHROPIC_API_KEY' if provider=='claude' else 'CODEX_API_KEY'
handle=adapter.launch(DecisionAgentLaunch(provider=provider,model=request.profile.model,run_id='qualification',request=request,request_binding=ParticipantRequestBinding(owner,'agents.operator')),{key:'sk-fixture-local-only'})
adapter.list_tools(handle)
schema={'type':'object','properties':{'candidate':{'type':'integer','minimum':0,'maximum':0}},'required':['candidate'],'additionalProperties':False}
if sys.argv[4]=='200':
    assert json.loads(adapter.respond(handle,'decision body',response_schema=schema))=={'candidate':0}
    usage=adapter.usage(handle)
    assert usage.input_tokens is not None and usage.input_tokens >= 12, repr(usage)
    assert usage.output_tokens is not None and usage.output_tokens >= 4, repr(usage)
    record=json.loads((store.get_run_path('qualification')/'workbench/usage.jsonl').read_text().splitlines()[-1])
    assert record['input_tokens']==usage.input_tokens and record['output_tokens']==usage.output_tokens
    assert record['participant_address']==request.configuration_result.participant_address
    assert record['configuration_digest']==request.configuration_result.configuration_digest
else:
    try:
        adapter.respond(handle,'decision body',response_schema=schema)
    except AgentExecutionError as error:
        assert 'sk-fixture' not in str(error)
    else:
        raise AssertionError('rejected native request unexpectedly succeeded')
adapter.close(handle)
"""
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                script,
                str(installed),
                str(executable),
                str(tmp_path),
                str(status),
            ],
            input=json.dumps(data),
            text=True,
            capture_output=True,
            cwd=tmp_path,
            timeout=150,
        )
        assert result.returncode == 0, (
            result.stderr,
            [(path, sorted(body)) for path, body in requests],
        )
    assert requests
    if status == 200:
        record = json.loads(
            (tmp_path / "runs/qualification/workbench/usage.jsonl")
            .read_text()
            .splitlines()[-1]
        )
        assert record["input_tokens"] == 12 * len(requests)
        assert record["output_tokens"] == 4 * len(requests)
    assert all(body["model"] == model for _, body in requests)
    assert all(
        "temperature" not in body and "top_p" not in body for _, body in requests
    )
    body = requests[-1][1]
    if provider == "claude":
        assert body["output_config"]["effort"] == effort
        assert "exact author prefix\\ndecision body" in json.dumps(body["messages"])
    else:
        assert body["reasoning"]["effort"] == (effort if mode == "effort" else "none")
        assert "exact author prefix\\ndecision body" in json.dumps(body["input"])
