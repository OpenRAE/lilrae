"""Native log limits preserve redacted content and artifact references."""

from subprocess import CompletedProcess
from types import SimpleNamespace
from dataclasses import replace
import json
import pytest
from aptl.core.evidence.adapters.builtins import ContainerLogSource, ContainerFileSource
from aptl.core.evidence.adapters.sources import WindowedQueryCollector
from aptl.core.evidence.coordinator import acquire_evidence
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.experiment.capture_registry import CaptureLimits
from aptl.core.runstore import LocalRunStore
from tests.test_evidence_coordinator import _binding, _SCOPE, _CLOCK


@pytest.mark.parametrize("kind", ["logs", "file"])
@pytest.mark.parametrize("failed", [False, True])
def test_large_native_exports_keep_safe_prefix_within_artifact_budget(
    tmp_path, kind, failed
):
    output = "accepted password=private-canary " + "event " * 1000
    operations = SimpleNamespace(
        container_logs_capture=lambda *a, **k: CompletedProcess(
            [], 1 if failed else 0, output, ""
        ),
        container_exec=lambda *a, **k: CompletedProcess(
            [], 1 if failed else 0, output, ""
        ),
    )
    source = (
        ContainerLogSource(operations, ["soc"])
        if kind == "logs"
        else ContainerFileSource(
            operations,
            [("soc", "/var/log/events")],
            max_bytes=4096,
            timestamp_of=lambda line: "2026-07-20T00:00:00Z",
        )
    )
    binding = replace(
        _binding(redaction_required=True, redaction_policy="redact_secrets"),
        limits=CaptureLimits(1024, 10, 60),
    )
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
    assert result.reports[0].status is CollectorStatus.TRUNCATION
    retained = (
        store.get_run_path(_SCOPE.run_id) / result.refs[0].content_uri
    ).read_bytes()
    assert len(retained) <= 1024
    assert b"private-canary" not in retained
    assert json.loads(retained)
    assert b"accepted" in retained


def test_failed_file_read_keeps_accepted_stdout(tmp_path):
    operations = SimpleNamespace(
        container_exec=lambda *a, **k: CompletedProcess(
            [], 1, "accepted before failure", "private diagnostic"
        )
    )
    source = ContainerFileSource(
        operations,
        [("soc", "/var/log/events")],
        timestamp_of=lambda line: "2026-07-20T00:00:00Z",
    )
    binding = _binding()
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
    assert result.reports[0].status is CollectorStatus.SOURCE_UNAVAILABLE
    retained = (
        store.get_run_path(_SCOPE.run_id) / result.refs[0].content_uri
    ).read_bytes()
    assert (
        b"accepted before failure" in retained and b"private diagnostic" not in retained
    )


@pytest.mark.parametrize("timed_out", [False, True])
def test_source_bounds_precede_processing_ceiling_and_preserve_healthy_peers(
    tmp_path, monkeypatch, timed_out
):
    import aptl.core.evidence._persist as persistence
    from subprocess import TimeoutExpired

    monkeypatch.setattr(persistence, "_MAX_REDACTION_BYTES", 4096)
    large = "accepted password=private-canary " + "event " * 10000

    def read(container, **kwargs):
        if container == "large" and timed_out:
            raise TimeoutExpired("safe command", 30, output=large, stderr="")
        return CompletedProcess(
            [], 0, large if container == "large" else "healthy peer data", ""
        )

    source = ContainerLogSource(
        SimpleNamespace(container_logs_capture=read), ["large", "healthy"]
    )
    binding = replace(
        _binding(redaction_required=True, redaction_policy="redact_secrets"),
        limits=CaptureLimits(4096, 10, 60),
    )
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
    assert result.reports[0].status is CollectorStatus.TRUNCATION
    retained = (
        store.get_run_path(_SCOPE.run_id) / result.refs[0].content_uri
    ).read_bytes()
    assert b"accepted" in retained and b"healthy peer data" in retained
    assert b"private-canary" not in retained
    assert len(retained) <= 4096


def test_native_backend_file_timeout_retains_accepted_output(tmp_path, monkeypatch):
    from subprocess import TimeoutExpired
    from aptl.core.deployment.docker_compose import DockerComposeBackend
    from aptl.backends.scenario_runtime_hooks import AdmittedRuntimeOperations

    backend = DockerComposeBackend(project_dir=tmp_path, project_name="test")
    monkeypatch.setattr(
        backend, "_resolve_owned_container_id", lambda name: "owned-soc"
    )

    def timed_out(command, **kwargs):
        raise TimeoutExpired(
            command,
            kwargs["timeout"],
            output=b"accepted native file prefix\n",
            stderr=b"",
        )

    monkeypatch.setattr("subprocess.run", timed_out)
    operations = AdmittedRuntimeOperations(backend, [SimpleNamespace(name="soc")])
    source = ContainerFileSource(
        operations,
        [("soc", "/var/log/events")],
        timestamp_of=lambda line: "2026-07-20T00:00:00Z",
    )
    result = source.fetch("2026-07-20T00:00:00Z", "2026-07-20T00:01:00Z")
    assert result.status is CollectorStatus.TIMEOUT
    assert result.records[0]["output"] == "accepted native file prefix\n"
