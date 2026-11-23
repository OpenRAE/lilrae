"""Native log and file captures retain complete, redacted content."""

from types import SimpleNamespace
import json

import pytest

from aptl.core.deployment._compose_log_capture import StreamExit
from aptl.core.evidence.adapters.builtins import ContainerLogSource, ContainerFileSource
from aptl.core.evidence.adapters.sources import WindowedQueryCollector
from aptl.core.evidence.coordinator import acquire_evidence
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.runstore import LocalRunStore
from tests.test_evidence_coordinator import _binding, _SCOPE, _CLOCK

_WINDOW_TIME = "2026-07-20T00:00:00Z"


def _streams(outputs: dict[str, tuple[bytes, bytes, StreamExit]]) -> SimpleNamespace:
    """Return native operations that stream fixed output per container."""

    def stream(name, *args, stdout, stderr, **kwargs):
        out, err, exit = outputs[name]
        stdout.write(out)
        stderr.write(err)
        return exit

    return SimpleNamespace(container_logs_stream=stream, container_exec_stream=stream)


def _acquire(tmp_path, source, binding):
    store = LocalRunStore(tmp_path / "runs")
    result = acquire_evidence(
        bindings=[binding],
        collectors={
            binding.registration_id: WindowedQueryCollector(
                binding.registration_id, source
            )
        },
        scope=_SCOPE,
        clock=_CLOCK,
        run_store=store,
    )
    retained = (
        store.get_run_path(_SCOPE.run_id) / result.refs[0].content_uri
    ).read_bytes()
    return result, retained


@pytest.mark.parametrize("kind", ["logs", "file"])
def test_large_native_exports_are_retained_completely_and_redacted(tmp_path, kind):
    events = 100_000
    output = b"accepted password=private-canary\n" + b"event\n" * events
    operations = _streams({"soc": (output, b"", StreamExit(0, False, False))})
    source = (
        ContainerLogSource(operations, ["soc"])
        if kind == "logs"
        else ContainerFileSource(
            operations,
            [("soc", "/var/log/events")],
            timestamp_of=lambda line: _WINDOW_TIME,
        )
    )
    binding = _binding(redaction_required=True, redaction_policy="redact_secrets")
    result, retained = _acquire(tmp_path, source, binding)
    expected = CollectorStatus.OK if kind == "logs" else CollectorStatus.MID_RUN_LOSS
    assert result.reports[0].status is expected
    assert b"private-canary" not in retained
    record = json.loads(retained)[0]
    assert record["output"].startswith("accepted")
    assert record["output"].count("event\n") == events


def test_failed_file_read_keeps_accepted_stdout(tmp_path):
    operations = _streams(
        {
            "soc": (
                b"accepted before failure\n",
                b"private diagnostic",
                StreamExit(1, False, False),
            )
        }
    )
    source = ContainerFileSource(
        operations,
        [("soc", "/var/log/events")],
        timestamp_of=lambda line: _WINDOW_TIME,
    )
    result, retained = _acquire(tmp_path, source, _binding())
    assert result.reports[0].status is CollectorStatus.SOURCE_UNAVAILABLE
    assert b"accepted before failure" in retained
    assert b"private diagnostic" not in retained


def test_stalled_peer_keeps_its_complete_output_and_the_healthy_peer(tmp_path):
    large = b"accepted password=private-canary\n" + b"event\n" * 50_000
    operations = _streams(
        {
            "large": (large, b"", StreamExit(None, True, False)),
            "healthy": (b"healthy peer data", b"", StreamExit(0, False, False)),
        }
    )
    source = ContainerLogSource(operations, ["large", "healthy"])
    binding = _binding(redaction_required=True, redaction_policy="redact_secrets")
    result, retained = _acquire(tmp_path, source, binding)
    assert result.reports[0].status is CollectorStatus.TIMEOUT
    records = {row["container"]: row for row in json.loads(retained)}
    assert records["large"]["status"] == "timeout"
    assert records["large"]["output"].count("event\n") == 50_000
    assert records["healthy"]["output"] == "healthy peer data"
    assert b"private-canary" not in retained


def test_native_backend_file_timeout_retains_accepted_output(tmp_path, monkeypatch):
    from aptl.core.deployment.docker_compose import DockerComposeBackend
    from aptl.backends.scenario_runtime_hooks import AdmittedRuntimeOperations
    import aptl.core.deployment._compose_queries as queries

    backend = DockerComposeBackend(project_dir=tmp_path, project_name="test")
    monkeypatch.setattr(
        backend, "_resolve_owned_container_id", lambda name: "owned-soc"
    )

    def stalled(command, *, stdout, stderr, **kwargs):
        stdout.write(b"accepted native file prefix\n")
        return StreamExit(None, True, False)

    monkeypatch.setattr(queries, "stream_command", stalled)
    operations = AdmittedRuntimeOperations(backend, [SimpleNamespace(name="soc")])
    source = ContainerFileSource(
        operations,
        [("soc", "/var/log/events")],
        timestamp_of=lambda line: _WINDOW_TIME,
    )
    result = source.fetch(_WINDOW_TIME, "2026-07-20T00:01:00Z")
    assert result.status is CollectorStatus.TIMEOUT
    record = json.loads(b"".join(result.chunks))[0]
    assert record["output"] == "accepted native file prefix\n"
