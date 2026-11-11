"""The pinned transport observer preserves requests, responses and failures."""

from pathlib import Path
import subprocess
import json

import pytest


def test_capture_plugin_transport_contract(tmp_path):
    result = subprocess.run(
        [
            "node",
            "--test",
            str(Path(__file__).parent / "fixtures/opencode/capture-plugin.test.mjs"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _frames(*, usage=None, terminal=True):
    rows = [
        {"kind": "capture-ready", "request_id": None},
        {
            "kind": "request",
            "request_id": "request-1",
            "body": json.dumps(
                {
                    "model": "requested",
                    "max_tokens": 64,
                    "messages": [{"role": "user", "content": "private-credential"}],
                }
            ),
        },
        {
            "kind": "response",
            "request_id": "request-1",
            "json": json.dumps(
                {
                    "id": "generation-1",
                    "model": "served",
                    "provider": "observed-provider",
                    "usage": usage,
                }
            ),
        },
    ]
    if terminal:
        rows.append(
            {"kind": "request-finished", "request_id": "request-1", "status": 200}
        )
    for index, row in enumerate(rows):
        row.update(
            invocation_id="outer-red",
            sequence=index,
            observed_at="2026-11-03T12:00:00Z",
            monotonic_ms=index,
        )
    return b"\n".join(json.dumps(row).encode() for row in rows)


def test_per_call_usage_preserves_controls_claims_and_optional_billing():
    from aptl.workbench.provider_capture import reduce_provider_capture

    capture = reduce_provider_capture(
        _frames(usage={"prompt_tokens": 12, "completion_tokens": 3}),
        invocation_id="outer-red",
        secrets=("private-credential",),
        max_bytes=65536,
    )
    assert capture.complete
    assert capture.required_usage_complete
    call = capture.calls[0]
    assert call["request_controls"]["model"] == "requested"
    assert call["provider_claims"]["served_model"] == "served"
    assert call["input_tokens"] == 12
    assert call["output_tokens"] == 3
    assert call["cost"] is None
    assert call["cost_unavailable_reason"]
    reasons = {row["field"]: row["reason"] for row in call["unavailable_reasons"]}
    assert reasons["reasoning_tokens"]
    assert reasons["cache_read_tokens"]
    assert "private-credential" not in repr(capture.records)


@pytest.mark.parametrize(
    "usage",
    [None, {"prompt_tokens": True, "completion_tokens": 3}, {"prompt_tokens": 12}],
)
def test_completed_calls_require_real_prompt_and_completion_counts(usage):
    from aptl.workbench.provider_capture import reduce_provider_capture

    capture = reduce_provider_capture(
        _frames(usage=usage), invocation_id="outer-red", secrets=(), max_bytes=65536
    )
    assert capture.complete
    assert not capture.required_usage_complete


def test_timeout_keeps_accepted_records_without_inventing_terminal_usage():
    from aptl.workbench.provider_capture import reduce_provider_capture

    capture = reduce_provider_capture(
        _frames(terminal=False), invocation_id="outer-red", secrets=(), max_bytes=65536
    )
    assert not capture.complete
    assert capture.records
    assert capture.calls[0]["state"] == "unsettled"


def test_unavailable_provider_claims_keep_explicit_reasons():
    from aptl.workbench.provider_capture import reduce_provider_capture

    rows = [
        json.loads(line)
        for line in _frames(
            usage={"prompt_tokens": 12, "completion_tokens": 3}
        ).splitlines()
    ]
    rows[2]["json"] = json.dumps(
        {"usage": {"prompt_tokens": 12, "completion_tokens": 3}}
    )
    capture = reduce_provider_capture(
        b"\n".join(json.dumps(row).encode() for row in rows),
        invocation_id="outer-red",
        secrets=(),
        max_bytes=65536,
    )
    call = capture.calls[0]
    assert call["provider_claims"] == {
        "generation_id": None,
        "served_model": None,
        "served_provider": None,
    }
    reasons = {row["field"]: row["reason"] for row in call["unavailable_reasons"]}
    assert all(reasons[key] for key in call["provider_claims"])


def test_oversized_raw_capture_keeps_complete_accepted_frames():
    from aptl.workbench.provider_capture import reduce_provider_capture

    accepted = _frames(usage={"prompt_tokens": 12, "completion_tokens": 3})
    result = reduce_provider_capture(
        accepted + b"x" * 1000,
        invocation_id="outer-red",
        secrets=(),
        max_bytes=len(accepted) + 1,
    )
    assert not result.complete
    assert result.records
    assert result.calls[0]["input_tokens"] == 12


def test_malformed_optional_billing_does_not_fail_successful_opencode_response():
    from aptl.workbench.opencode_events import parse_opencode_response

    events = [
        {"type": "text", "part": {"text": "done"}},
        {
            "type": "step_finish",
            "part": {
                "reason": "stop",
                "tokens": {"input": 12, "output": 3},
                "cost": "unavailable",
            },
        },
    ]
    response = parse_opencode_response(
        b"\n".join(json.dumps(row).encode() for row in events)
    )
    assert response.valid
    assert response.cost is None
    assert response.input_tokens == 12
