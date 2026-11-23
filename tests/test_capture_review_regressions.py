"""Regression evidence for the four required capture review fixes."""

import json
from subprocess import CompletedProcess
from types import SimpleNamespace

import pytest

from aptl.core.evidence.adapters.sources import (
    CallableWindowedSource,
    SourceResult,
    WindowedQueryCollector,
)
from aptl.core.evidence.coordinator import acquire_evidence
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.runstore import LocalRunStore
from tests.test_evidence_coordinator import _CLOCK, _SCOPE, _binding
from tests.test_participant_capture import _grant, _payload


def test_failed_invocation_publication_remains_incomplete_after_reopen(
    tmp_path, monkeypatch
):
    from aptl.core.evidence.participant_capture import ParticipantCaptureArchive

    store = LocalRunStore(tmp_path / "runs")
    archive = ParticipantCaptureArchive(store, _grant())
    archive.record(_payload())
    archive.expect_invocation("second")
    original = store.create_run_json_once

    def write(run, path, value):
        if "/participant-capture/" in path and value.get("invocation_id") == "second":
            raise OSError("private write failure")
        return original(run, path, value)

    monkeypatch.setattr(store, "create_run_json_once", write)
    later = _payload()
    later["invocation_id"] = "second"
    with pytest.raises(OSError):
        archive.record(later)
    result = ParticipantCaptureArchive(store, _grant()).fetch("start", "end")
    assert result.status is CollectorStatus.MID_RUN_LOSS
    totals = result.records[0]["totals"]
    assert totals["membership_complete"] is False
    assert totals["input_tokens"] is None
    assert totals["known_input_tokens_subtotal"] == 12


@pytest.mark.parametrize("interrupted", [False, True])
def test_split_stream_credentials_cannot_be_reconstructed(interrupted):
    from aptl.workbench.provider_capture import reduce_provider_capture
    from tests.test_provider_capture import _frames

    rows = [
        json.loads(line)
        for line in _frames(
            usage={"prompt_tokens": 12, "completion_tokens": 3}
        ).splitlines()
    ]
    rows[1]["body"] = rows[1]["body"].replace("private-credential", "safe user prompt")
    terminal = rows.pop()
    template = rows.pop()
    for fragment in ("granted-", "private-", "canary"):
        frame = {
            **template,
            "json": json.dumps(
                {
                    "id": "generation-1",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": fragment},
                            "finish_reason": None,
                        }
                    ],
                }
            ),
        }
        rows.append(frame)
    if not interrupted:
        rows.append(
            {
                **template,
                "json": json.dumps(
                    {
                        "id": "generation-1",
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 12, "completion_tokens": 3},
                    }
                ),
            }
        )
        rows.append(terminal)
    for index, row in enumerate(rows):
        row["sequence"] = index
    result = reduce_provider_capture(
        b"\n".join(json.dumps(row).encode() for row in rows),
        invocation_id="outer-red",
        secrets=("granted-private-canary",),
    )
    retained = json.dumps(result.records)
    assert "granted-" not in retained
    assert "private-" not in retained
    assert "canary" not in retained
    assert result.calls


@pytest.mark.parametrize("operation", ["logs", "file"])
@pytest.mark.parametrize("failure", [None, "timeout", "interrupted"])
def test_incomplete_native_secret_blocks_are_withheld_in_artifacts(
    tmp_path, operation, failure
):
    from aptl.core.evidence.adapters.builtins import (
        ContainerFileSource,
        ContainerLogSource,
    )
    from aptl.core.deployment._compose_log_capture import StreamExit

    payload = b"public record\n-----BEGIN PRIVATE KEY-----\n" + b"QUJDREVGR0g=\n" * 20

    def stream(*args, stdout, stderr, **kwargs):
        stdout.write(payload)
        return StreamExit(
            None if failure else 0, failure == "timeout", failure == "interrupted"
        )

    ops = SimpleNamespace(container_exec_stream=stream, container_logs_stream=stream)
    source = (
        ContainerLogSource(ops, ["soc"])
        if operation == "logs"
        else ContainerFileSource(
            ops,
            [("soc", "/var/log/events")],
            timestamp_of=lambda line: "2026-07-20T00:00:00Z",
        )
    )
    binding = _binding(redaction_required=True, redaction_policy="redact_secrets")
    store = LocalRunStore(tmp_path / "runs")
    result = acquire_evidence(
        bindings=[binding],
        collectors={
            binding.registration_id: WindowedQueryCollector(
                binding.registration_id, source
            )
        },
        run_store=store,
        scope=_SCOPE,
        clock=_CLOCK,
    )
    retained = (
        store.get_run_path(_SCOPE.run_id) / result.refs[0].content_uri
    ).read_bytes()
    assert b"public record" in retained
    assert b"QUJDREVGR0g=" not in retained
    if failure is not None:
        assert result.reports[0].status is not CollectorStatus.OK


@pytest.mark.parametrize("operation", ["logs", "exec", "input"])
def test_capture_keeps_native_operation_timeouts_and_store_progress_timeout(
    tmp_path, monkeypatch, operation
):
    import io

    from aptl.core.deployment.docker_compose import DockerComposeBackend
    from aptl.core.deployment._compose_log_capture import StreamExit
    from aptl.backends.scenario_runtime_hooks import AdmittedRuntimeOperations
    import aptl.core.deployment._compose_queries as queries

    backend = DockerComposeBackend(project_dir=tmp_path, project_name="test")
    receipt = SimpleNamespace(native_id="owned-soc")
    ownership = SimpleNamespace(candidates=lambda *a, **k: (receipt,))
    monkeypatch.setattr(backend, "_ensure_resource_ownership", lambda: ownership)
    monkeypatch.setattr(backend, "_ownership_daemon_id", lambda: "daemon")
    monkeypatch.setattr(backend, "_container_receipt_is_current", lambda *a: True)
    seen = []

    def run(command, **kwargs):
        seen.append((command[:2], kwargs["timeout"]))
        return CompletedProcess(command, 0, '{"Id":"owned-soc"}', "")

    def stream(command, **kwargs):
        seen.append((command[:2], kwargs["progress_timeout"]))
        return StreamExit(0, False, False)

    monkeypatch.setattr("subprocess.run", run)
    monkeypatch.setattr(queries, "stream_command", stream)
    operations = AdmittedRuntimeOperations(backend, [SimpleNamespace(name="soc")])

    def fetch(*args):
        if operation == "logs":
            operations.container_logs_stream(
                "soc", since=None, until=None, stdout=io.BytesIO(), stderr=io.BytesIO()
            )
        elif operation == "exec":
            operations.container_exec("soc", ["true"], timeout=30)
        else:
            operations.container_exec_with_input("soc", ["cat"], "input", timeout=30)
        return SourceResult(
            status=CollectorStatus.OK, records=[{"message": "accepted"}]
        )

    binding = _binding()
    result = acquire_evidence(
        bindings=[binding],
        collectors={
            binding.registration_id: WindowedQueryCollector(
                binding.registration_id, CallableWindowedSource(fetch)
            )
        },
        run_store=LocalRunStore(tmp_path / "runs", progress_timeout_seconds=42.0),
        scope=_SCOPE,
        clock=_CLOCK,
    )
    assert result.reports[0].status is CollectorStatus.OK
    expected = (["docker", "logs"], 42.0) if operation == "logs" else (
        ["docker", "exec"], 30
    )
    assert seen[-1] == expected


@pytest.mark.parametrize("complete", [False, True])
def test_cli_content_is_redacted_after_reassembly(complete):
    from aptl.workbench.provider_content_redaction import redact_cli_content

    events = [
        {"type": "text", "part": {"text": part}}
        for part in ("granted-", "private-", "canary")
    ]
    retained = redact_cli_content(
        events, ("granted-private-canary",), complete=complete
    )
    encoded = json.dumps(retained)
    assert "granted-" not in encoded
    assert "private-" not in encoded
    assert "canary" not in encoded
    assert retained[-1]["part"]["text"]
