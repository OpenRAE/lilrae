"""Source-read time belongs to the admitted collection deadline."""

from dataclasses import replace
from types import SimpleNamespace
from subprocess import CompletedProcess
import json
import pytest
from aptl.backends.scenario_runtime_hooks import AdmittedRuntimeOperations
from aptl.core.evidence.adapters.builtins import ContainerLogSource
from aptl.core.evidence.adapters.sources import WindowedQueryCollector
from aptl.core.evidence.coordinator import acquire_evidence
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.experiment.capture_registry import CaptureLimits
from aptl.core.runstore import LocalRunStore
from tests.test_evidence_coordinator import _binding, _SCOPE


def test_slow_native_read_obeys_remaining_timeout_and_retains_late_prefix(
    tmp_path, monkeypatch
):
    import aptl.core.evidence.adapters.sources as owner

    elapsed = [0.0]
    monkeypatch.setattr(owner, "monotonic", lambda: elapsed[0])
    timeouts = []

    class Clock:
        def now(self):
            return f"2026-11-04T00:00:0{int(elapsed[0])}Z"

    def read(*args, **kwargs):
        timeouts.append(kwargs["timeout"])
        elapsed[0] += 2.0  # A source that does not raise its own timeout.
        return CompletedProcess([], 0, "accepted prefix", "")

    operations = AdmittedRuntimeOperations(
        SimpleNamespace(container_logs_capture=read), [SimpleNamespace(name="soc")]
    )
    binding = replace(_binding(), limits=CaptureLimits(4096, 10, 1))
    collector = WindowedQueryCollector(
        binding.registration_id, ContainerLogSource(operations, ["soc"])
    )
    store = LocalRunStore(tmp_path / "runs")
    result = acquire_evidence(
        bindings=[binding],
        collectors={binding.registration_id: collector},
        scope=_SCOPE,
        clock=Clock(),
        run_store=store,
    )
    assert timeouts == [1.0]
    assert result.reports[0].status is CollectorStatus.TIMEOUT
    assert result.reports[0].scope == _SCOPE
    assert result.records[0].captured_at == "2026-11-04T00:00:02Z"
    assert result.refs[0].attempt_id == _SCOPE.attempt_id
    retained = json.loads(
        (store.get_run_path(_SCOPE.run_id) / result.refs[0].content_uri).read_bytes()
    )
    assert retained[0]["output"] == "accepted prefix"


@pytest.mark.parametrize("exhausted_by", ["trial", "peer"])
def test_deadline_exhaustion_keeps_already_captured_participant_artifacts(
    tmp_path, monkeypatch, exhausted_by
):
    import aptl.core.evidence.adapters.sources as owner
    from aptl.core.evidence.participant_capture import ParticipantCaptureArchive
    from tests.test_participant_capture import _grant, _payload
    from aptl.core.evidence.adapters.sources import CallableWindowedSource

    elapsed = [0.0]
    monkeypatch.setattr(owner, "monotonic", lambda: elapsed[0])
    binding = replace(_grant().binding, limits=CaptureLimits(4096, 10, 1))
    store = LocalRunStore(tmp_path / "runs")
    archive = ParticipantCaptureArchive(
        store, replace(_grant(), binding=binding, scope=_SCOPE)
    )
    archive.record(_payload())
    bindings = [binding]
    collectors = {
        binding.registration_id: WindowedQueryCollector(
            binding.registration_id, archive
        )
    }

    def exhaust():
        elapsed[0] = 2.0

    if exhausted_by == "peer":
        peer = replace(binding, registration_id="peer", requirement_id="peer")

        def slow_peer(*args):
            exhaust()
            raise OSError("private peer failure")

        bindings.append(peer)
        collectors[peer.registration_id] = WindowedQueryCollector(
            peer.registration_id, CallableWindowedSource(slow_peer)
        )
    from tests.test_evidence_coordinator import _CLOCK

    result = acquire_evidence(
        bindings=bindings,
        collectors=collectors,
        run_store=store,
        scope=_SCOPE,
        clock=_CLOCK,
        trial_body=exhaust if exhausted_by == "trial" else lambda: None,
    )
    assert result.reports[0].status is CollectorStatus.TIMEOUT
    assert result.refs[0].attempt_id == _SCOPE.attempt_id
    retained = json.loads(
        (store.get_run_path(_SCOPE.run_id) / result.refs[0].content_uri).read_bytes()
    )
    assert retained[0]["invocations"][0]["invocation_id"] == "outer-red"
    assert retained[0]["totals"]["input_tokens"] == 12
    assert "private peer failure" not in repr(result)
