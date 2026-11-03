"""Safe provider observations preserve actual controls and call membership."""

import hashlib
import json

import pytest


def events():
    controls = {
        "model": "test/model",
        "provider": {
            "only": ["test-provider"],
            "order": ["test-provider"],
            "allow_fallbacks": False,
            "require_parameters": True,
        },
        "max_tokens": 128,
        "stream": True,
    }
    return [
        {"kind": "ready", "observer_sha256": "a" * 64},
        {
            "kind": "request",
            "call_id": 1,
            "timestamp_ms": 10,
            "controls": controls,
            "context": [
                {
                    "role": "user",
                    "content_sha256": hashlib.sha256(b"private prompt").hexdigest(),
                    "authored_prefix_sha256": hashlib.sha256(
                        b"private prompt"
                    ).hexdigest(),
                }
            ],
        },
        {
            "kind": "response",
            "call_id": 1,
            "timestamp_ms": 11,
            "http_status": 200,
            "response": {
                "generation_id": "gen-fixture",
                "model": "test/served",
                "input_tokens": 12,
                "output_tokens": 3,
                "reasoning_tokens": 0,
                "cost": 0.125,
                "finish_reason": "stop",
            },
        },
        {"kind": "end", "call_id": 1, "timestamp_ms": 12, "state": "completed"},
    ]


def read(tmp_path, data=None, **kwargs):
    from aptl.workbench.opencode_observation import read_request_observations

    if data is not None:
        (tmp_path / "provider-observations.jsonl").write_text(
            "\n".join(json.dumps(e) for e in data) + "\n"
        )
    return read_request_observations(tmp_path, observer_sha256="a" * 64, **kwargs)


def test_actual_controls_and_response_usage_are_joined_without_raw_content(tmp_path):
    observed = read(tmp_path, events())
    assert observed.status == "observed"
    (call,) = observed.calls
    assert call.controls.max_tokens == 128
    assert "temperature" not in call.controls.model_fields_set
    assert call.response.generation_id == "gen-fixture"
    assert call.response.model == "test/served"
    assert call.response.reasoning_tokens == 0
    assert call.response.provider is None
    assert call.response.cost == 0.125
    observed.require_fields(
        frozenset({"outgoing_controls", "provider_generation_id", "input_tokens"})
    )
    with pytest.raises(ValueError, match="unavailable"):
        observed.require_fields(frozenset({"served_provider_claim"}))
    assert "private prompt" not in repr(observed)


@pytest.mark.parametrize(
    "change", ["unknown", "wrong-observer", "peer-call", "duplicate", "after-end"]
)
def test_malformed_or_unbound_records_cannot_look_complete(tmp_path, change):
    data = events()
    if change == "unknown":
        data[1]["credential"] = "private-test-credential"
    elif change == "wrong-observer":
        data[0]["observer_sha256"] = "b" * 64
    elif change == "peer-call":
        data[2]["call_id"] = 2
    elif change == "duplicate":
        data.insert(2, data[1])
    else:
        data.append(data[2])
    observed = read(tmp_path, data)
    assert observed.status == "invalid"
    assert observed.calls == ()
    assert "private-test-credential" not in repr(observed)


def test_interrupted_calls_keep_safe_membership_and_missing_values(tmp_path):
    observed = read(tmp_path, events()[:2])
    assert observed.status == "partial"
    assert len(observed.calls) == 1
    assert observed.calls[0].state == "dispatched"
    assert observed.calls[0].response is None


def test_missing_symlink_and_oversized_observations_are_closed(tmp_path):
    assert read(tmp_path).status == "missing"
    target = tmp_path / "provider-observations.jsonl"
    target.symlink_to("/dev/null")
    assert read(tmp_path).status == "invalid"
    target.unlink()
    read(tmp_path, events())
    assert read(tmp_path, max_bytes=1).status == "oversized"


def test_truncated_tail_preserves_prior_call_membership(tmp_path):
    read(tmp_path, events()[:2])
    with (tmp_path / "provider-observations.jsonl").open("ab") as stream:
        stream.write(b'{"kind":"response"')
    result = read(tmp_path)
    assert result.status == "partial"
    assert len(result.calls) == 1


def test_parent_checks_observed_controls_against_its_independent_expectation(tmp_path):
    from aptl.core.provider_observation import ObservedRequestControls

    expected = ObservedRequestControls.model_validate_json(
        json.dumps(events()[1]["controls"])
    )
    changed = events()
    changed[1]["controls"]["max_tokens"] = 64
    assert read(tmp_path, changed, expected_controls=expected).status == "invalid"


def synthetic_journal(work):
    """Model native reports only for process doubles in trial ownership tests."""
    data = events()
    inputs = json.loads((work / "observer-input.json").read_text())
    data[0]["observer_sha256"] = inputs["observer_sha256"]
    data[1]["controls"] = inputs["controls"]
    data[1]["context"][0]["authored_prefix_sha256"] = inputs["prompt_sha256"]
    (work / "provider-observations.jsonl").write_text(
        "\n".join(json.dumps(e) for e in data) + "\n"
    )


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "wrong-control",
        "wrong-prefix",
        "wrong-extra",
        "redacted-id",
        "redacted-capability",
        "cancelled",
        "turn-limit",
    ],
)
def test_plugin_observes_actual_fetch_and_never_keeps_secret_content(tmp_path, case):
    import subprocess
    from aptl.core.opencode import OpenRouterRoute
    from aptl.workbench.opencode_configuration import (
        render_opencode_config,
        opencode_environment,
    )
    from aptl.workbench.opencode_observation import (
        install_request_observer,
        read_request_observations,
    )

    config = render_opencode_config(
        "openrouter/test/model",
        OpenRouterRoute(
            endpoint="http://127.0.0.1:12345/api/v1", serving_provider="test-provider"
        ),
        {"*": "deny"},
        {},
    )
    if case == "turn-limit":
        config["agent"] = {"build": {"steps": 1}}
    environment, _ = install_request_observer(
        tmp_path,
        config,
        opencode_environment(
            tmp_path, {"OPENROUTER_API_KEY": "private-test-credential"}, 128
        ),
        b"private prompt",
    )
    (tmp_path / "opencode.json").write_text(json.dumps(config))
    script = r"""
import {readFileSync} from 'node:fs';
const config = JSON.parse(readFileSync('./opencode.json', 'utf8'));
const inputs = JSON.parse(readFileSync('./observer-input.json', 'utf8'));
config.mcp={fixture:{environment:{LILRAE_TOOL_TOKEN:'tool-capability'}}};
let forwarded = 0;
const cancellation = new AbortController();
globalThis.fetch = async () => {
 forwarded++;
 if (process.argv[2] === 'cancelled') { cancellation.abort(); throw new Error('private-test-credential'); }
 const body = JSON.stringify({id:process.argv[2] === 'redacted-id' ? 'gen-private-test-credential' : process.argv[2] === 'redacted-capability' ? 'gen-tool-capability' : 'gen-observed',
  model:'test/served',provider:'test-provider',choices:[{index:0,delta:{content:'private reply and tool-capability'},finish_reason:'stop'}],
  usage:{prompt_tokens:12,completion_tokens:3,completion_tokens_details:{reasoning_tokens:0},cost:0.125}});
 const bytes = new TextEncoder().encode('data: '+body+'\r\n\r\ndata: [DONE]\r\n\r\n');
 return new Response(new ReadableStream({start(controller) {
  for (let i=0;i<bytes.length;i+=7) controller.enqueue(bytes.slice(i,i+7)); controller.close();
 }}),{headers:{'Content-Type':'text/event-stream'}});
};
const {RequestObserver} = await import('./request_observer.mjs');
const hooks = await RequestObserver(); await hooks.config(config);
const request = {...inputs.controls, messages:[{role:'system',content:'private system tool-capability'},
 {role:'user',content:process.argv[2] === 'wrong-prefix' ? 'other prompt' : 'private prompt'}]};
if (process.argv[2] === 'wrong-control') request.max_tokens=64;
if (process.argv[2] === 'wrong-extra') request.frequency_penalty=0.5;
let refused=false;
try {
 const response = await config.provider.openrouter.options.fetch(inputs.endpoint+'/chat/completions',
  {method:'POST',body:JSON.stringify(request),signal:cancellation.signal});
 await response.text();
 if (process.argv[2] === 'turn-limit') await config.provider.openrouter.options.fetch(inputs.endpoint+'/chat/completions',
  {method:'POST',body:JSON.stringify(request),signal:cancellation.signal});
} catch { refused=true; }
console.log(JSON.stringify({forwarded,refused}));
"""
    (tmp_path / "probe.mjs").write_text(script)
    result = subprocess.run(
        ["node", str(tmp_path / "probe.mjs"), case],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    summary = json.loads(result.stdout)
    if case.startswith("wrong-"):
        assert summary == {"forwarded": 0, "refused": True}
        return
    observed = read_request_observations(tmp_path)
    if case == "turn-limit":
        assert summary == {"forwarded": 1, "refused": True}
        assert observed.native_turn_limit == 1
    assert len(observed.calls) == 1
    call = observed.calls[0]
    if case == "cancelled":
        assert call.state == "cancelled"
        assert call.response is None
    else:
        assert observed.status == "observed"
        assert call.response.generation_id == (
            None if case in {"redacted-id", "redacted-capability"} else "gen-observed"
        )
        assert call.response.input_tokens == 12
        assert call.response.reasoning_tokens == 0
        assert call.response.cost == 0.125
    retained = (tmp_path / "provider-observations.jsonl").read_text()
    for private in (
        "private-test-credential",
        "private prompt",
        "private reply",
        "tool-capability",
    ):
        assert private not in retained


def test_missing_usage_is_unknown_and_cannot_satisfy_completed_call_capture(tmp_path):
    data = events()
    del data[2]["response"]["input_tokens"]
    result = read(tmp_path, data)
    assert result.calls[0].response.input_tokens is None
    with pytest.raises(ValueError, match="unavailable"):
        result.require_fields(frozenset({"input_tokens"}))


def test_failed_retry_membership_does_not_duplicate_completed_usage(tmp_path):
    data = events()
    first = [dict(item) for item in data]
    first[2] = {**first[2], "http_status": 429, "response": {}}
    first[3] = {**first[3], "state": "failed"}
    later = [
        {**item, "call_id": 2, "timestamp_ms": item["timestamp_ms"] + 10}
        for item in data[1:]
    ]
    result = read(tmp_path, first + later)
    assert result.status == "observed"
    assert [c.state for c in result.calls] == ["failed", "completed"]
    assert result.calls[0].response.input_tokens is None
    assert result.calls[1].response.input_tokens == 12
    result.require_fields(frozenset({"input_tokens", "provider_generation_id"}))


def test_journal_cannot_claim_more_completed_turns_than_its_observed_limit(tmp_path):
    data = events()
    data[0]["native_turn_limit"] = 1
    data += [
        {**item, "call_id": 2, "timestamp_ms": item["timestamp_ms"] + 10}
        for item in events()[1:]
    ]
    assert read(tmp_path, data).status == "invalid"


@pytest.mark.parametrize(
    "setting", ["native_history_required", "request_observation_required"]
)
def test_unqualified_observation_platform_fails_before_launch(
    tmp_path, monkeypatch, setting
):
    import sys
    from pathlib import Path
    from aptl.workbench.opencode_options import OpenCodeOptions

    monkeypatch.setattr(sys, "platform", "darwin")
    with pytest.raises(ValueError, match="qualified Linux"):
        OpenCodeOptions(
            executable=Path("/bin/true"), work_root=tmp_path, **{setting: True}
        )
