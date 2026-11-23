"""Capture time is bounded only by read progress, never by the trial length."""

from dataclasses import replace
from types import SimpleNamespace
import json
import pytest
from aptl.backends.scenario_runtime_hooks import AdmittedRuntimeOperations
from aptl.core.deployment._compose_log_capture import StreamExit
from aptl.core.evidence.adapters.builtins import ContainerLogSource
from aptl.core.evidence.adapters.sources import WindowedQueryCollector
from aptl.core.evidence.coordinator import acquire_evidence
from aptl.core.evidence.deadline import current_progress_timeout
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.runstore import LocalRunStore
from tests.test_evidence_coordinator import _CLOCK, _binding, _SCOPE


def test_slow_native_read_is_retained_and_sees_the_store_progress_timeout(tmp_path):
    elapsed = [0]
    observed = []

    class Clock:
        def now(self):
            return f"2026-11-04T00:{elapsed[0]:02d}:00Z"

    def stream(name, *, since, until, stdout, stderr):
        observed.append(current_progress_timeout())
        elapsed[0] += 30  # A read that takes far longer than any old budget.
        stdout.write(b"accepted complete output\n")
        return StreamExit(0, False, False)

    operations = AdmittedRuntimeOperations(
        SimpleNamespace(container_logs_stream=stream), [SimpleNamespace(name="soc")]
    )
    binding = _binding()
    collector = WindowedQueryCollector(
        binding.registration_id, ContainerLogSource(operations, ["soc"])
    )
    store = LocalRunStore(tmp_path / "runs", progress_timeout_seconds=90.0)
    result = acquire_evidence(
        bindings=[binding],
        collectors={binding.registration_id: collector},
        scope=_SCOPE,
        clock=Clock(),
        run_store=store,
    )
    assert observed == [90.0]
    assert result.reports[0].status is CollectorStatus.OK
    assert result.records[0].captured_at == "2026-11-04T00:30:00Z"
    assert result.refs[0].attempt_id == _SCOPE.attempt_id
    retained = json.loads(
        (store.get_run_path(_SCOPE.run_id) / result.refs[0].content_uri).read_bytes()
    )
    assert retained[0]["output"] == "accepted complete output\n"


@pytest.mark.parametrize("delayed_by", ["trial", "peer"])
def test_long_trial_or_failed_peer_keeps_participant_artifacts_complete(
    tmp_path, delayed_by
):
    import time

    from aptl.core.evidence.participant_capture import ParticipantCaptureArchive
    from tests.test_participant_capture import _grant, _payload
    from aptl.core.evidence.adapters.sources import CallableWindowedSource

    binding = _grant().binding
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

    if delayed_by == "peer":
        peer = replace(binding, registration_id="peer", requirement_id="peer")

        def failed_peer(*args):
            raise OSError("private peer failure")

        bindings.append(peer)
        collectors[peer.registration_id] = WindowedQueryCollector(
            peer.registration_id, CallableWindowedSource(failed_peer)
        )

    result = acquire_evidence(
        bindings=bindings,
        collectors=collectors,
        run_store=store,
        scope=_SCOPE,
        clock=_CLOCK,
        trial_body=(lambda: time.sleep(0.01)) if delayed_by == "trial" else lambda: None,
    )
    assert result.reports[0].status is CollectorStatus.OK
    assert result.refs[0].attempt_id == _SCOPE.attempt_id
    retained = json.loads(
        (store.get_run_path(_SCOPE.run_id) / result.refs[0].content_uri).read_bytes()
    )
    assert retained[0]["invocations"][0]["invocation_id"] == "outer-red"
    assert retained[0]["totals"]["input_tokens"] == 12
    assert "private peer failure" not in repr(result)
