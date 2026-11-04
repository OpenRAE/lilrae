"""Regression evidence for the four required capture review fixes."""

from dataclasses import replace
import json
from subprocess import CompletedProcess, TimeoutExpired
from types import SimpleNamespace

import pytest

from aptl.core.evidence.adapters.sources import (
    CallableWindowedSource,
    SourceResult,
    WindowedQueryCollector,
)
from aptl.core.evidence.coordinator import acquire_evidence
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.experiment.capture_registry import CaptureLimits
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
    assert totals["membership_complete"] is False and totals["input_tokens"] is None
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
        max_bytes=65536,
    )
    retained = json.dumps(result.records)
    assert (
        "granted-" not in retained
        and "private-" not in retained
        and "canary" not in retained
    )
    assert result.calls


@pytest.mark.parametrize("operation", ["logs", "file"])
@pytest.mark.parametrize("failure", ["overflow", "timeout", "interrupted"])
def test_incomplete_native_secret_blocks_are_withheld_in_artifacts(
    tmp_path, operation, failure
):
    from aptl.core.evidence.adapters.builtins import (
        ContainerFileSource,
        ContainerLogSource,
    )
    from aptl.core.deployment._compose_log_capture import LogCapture

    payload = "public record\n-----BEGIN PRIVATE KEY-----\n" + "QUJDREVGR0g=\n" * 20

    def read(*args, **kwargs):
        if failure == "timeout":
            raise TimeoutExpired("read", 30, output=payload, stderr="")
        if failure == "interrupted":
            error = InterruptedError("read")
            error.stdout, error.stderr = payload, ""
            raise error
        result = LogCapture([], 0, payload, "")
        result.truncated = True
        return result

    ops = SimpleNamespace(container_exec=read, container_logs_capture=read)
    source = (
        ContainerLogSource(ops, ["soc"])
        if operation == "logs"
        else ContainerFileSource(
            ops,
            [("soc", "/var/log/events")],
            max_bytes=100,
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
    assert b"public record" in retained and b"QUJDREVGR0g=" not in retained
    assert result.reports[0].status is not CollectorStatus.OK


@pytest.mark.parametrize("operation", ["logs", "exec", "input"])
@pytest.mark.parametrize("inspection_timeout", [False, True])
def test_capture_budget_covers_ownership_inspection_and_final_command(
    tmp_path, monkeypatch, operation, inspection_timeout
):
    from aptl.core.deployment.docker_compose import DockerComposeBackend
    from aptl.backends.scenario_runtime_hooks import AdmittedRuntimeOperations
    import aptl.core.evidence.adapters.sources as source_owner
    import aptl.core.deployment._compose_resource_resolution as resolution
    import aptl.core.deployment._compose_log_capture as log_owner

    elapsed = [0.0]
    monkeypatch.setattr(source_owner, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(
        resolution.time,
        "sleep",
        lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds),
    )
    backend = DockerComposeBackend(project_dir=tmp_path, project_name="test")
    receipt = SimpleNamespace(native_id="owned-soc")
    ownership = SimpleNamespace(candidates=lambda *a, **k: (receipt,))
    monkeypatch.setattr(backend, "_ensure_resource_ownership", lambda: ownership)
    monkeypatch.setattr(backend, "_ownership_daemon_id", lambda: "daemon")

    def current(owner, item):
        backend._raw_container_inspect(item.native_id)
        return True

    monkeypatch.setattr(backend, "_container_receipt_is_current", current)
    seen = []

    def run(command, **kwargs):
        seen.append((command[:2], kwargs["timeout"]))
        if command[:2] == ["docker", "inspect"]:
            elapsed[0] += 1.1 if inspection_timeout else 0.4
            if inspection_timeout:
                raise TimeoutExpired(command, kwargs["timeout"])
        return CompletedProcess(command, 0, '{"Id":"owned-soc"}', "")

    monkeypatch.setattr("subprocess.run", run)

    def logs(command, **kwargs):
        seen.append((command[:2], kwargs["timeout"]))
        return log_owner.LogCapture(command, 0, "accepted\n", "")

    monkeypatch.setattr(log_owner, "capture_logs", logs)
    operations = AdmittedRuntimeOperations(backend, [SimpleNamespace(name="soc")])

    def fetch(*args):
        if operation == "logs":
            operations.container_logs_capture("soc", timeout=30, max_bytes=4096)
        elif operation == "exec":
            operations.container_exec("soc", ["true"], timeout=30)
        else:
            operations.container_exec_with_input("soc", ["cat"], "input", timeout=30)
        return SourceResult(
            status=CollectorStatus.OK, records=[{"message": "accepted"}]
        )

    binding = replace(_binding(), limits=CaptureLimits(4096, 10, 1))
    result = acquire_evidence(
        bindings=[binding],
        collectors={
            binding.registration_id: WindowedQueryCollector(
                binding.registration_id, CallableWindowedSource(fetch)
            )
        },
        run_store=LocalRunStore(tmp_path / "runs"),
        scope=_SCOPE,
        clock=_CLOCK,
    )
    assert seen[0][0] == ["docker", "inspect"] and seen[0][1] == pytest.approx(1.0)
    if inspection_timeout:
        assert len(seen) == 1
        assert result.reports[0].status is CollectorStatus.TIMEOUT
    else:
        assert seen[-1][1] == pytest.approx(0.6)
        assert result.reports[0].status is CollectorStatus.OK


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
    assert (
        "granted-" not in encoded
        and "private-" not in encoded
        and "canary" not in encoded
    )
    assert retained[-1]["part"]["text"]
