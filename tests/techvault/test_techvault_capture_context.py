"""TechVault native sources consume the capture source context (#1705).

Both acquisition paths build the real TechVault sources through
``family_capture_sources``. Trial measurement must run every source without a
preparation effect; startup preparation must hand the phase to the sources.
"""

from __future__ import annotations

import subprocess
from dataclasses import replace
from types import SimpleNamespace

from aptl.core.correlation.clock import FixedClockProvider
from aptl.core.evidence.outcomes import AcquisitionPhase, CollectorStatus
from aptl.core.runstore import LocalRunStore
from tests.techvault.test_raes_evidence_acquisition import (
    _binding,
    _capture_selection,
)

_MISP = "aptl.collector.misp-authenticated-api-readiness"
_SURICATA = "aptl.collector.suricata-rule-readiness"
_SQLI = "aptl.collector.suricata-wazuh-sqli"
_WAZUH = "aptl.collector.wazuh-agent-readiness"
_NATIVE = (_MISP, _SURICATA, _SQLI, _WAZUH)


class _RecordingBackend:
    """A deployment backend that records every call and proves nothing."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def container_exec(self, name, cmd, *, timeout):
        self.calls.append(("exec", name, " ".join(cmd)))
        return subprocess.CompletedProcess(cmd, 1, "", "")

    def container_exec_with_input(self, name, cmd, payload, *, timeout):
        self.calls.append(("exec_with_input", name, " ".join(cmd) + "\n" + payload))
        return subprocess.CompletedProcess(cmd, 1, "", "")

    def container_image_digest(self, name):
        self.calls.append(("image_digest", name, ""))
        return None

    def container_inspect(self, name):
        self.calls.append(("inspect", name, ""))
        return {"State": {"Status": "running", "Running": True}}

    def effects(self) -> list[str]:
        """Return each recorded call that would change the range state."""

        markers = ("events/add", "UNION", "logger ")
        return [
            text for _kind, _name, text in self.calls if any(m in text for m in markers)
        ]

    def touched(self, name: str) -> bool:
        return any(call[1] == name for call in self.calls)


def _request(tmp_path, realization, backend, selection):
    from aptl.backends.raes_evidence_acquisition import NativeEvidenceRequest

    bindings = tuple(_binding(item, item.rsplit(".", 1)[-1]) for item in _NATIVE)
    plan = SimpleNamespace(
        plan_id="capture-plan-test",
        canonical_bytes=b"{}",
        runtime_bindings=lambda: bindings,
    )
    return NativeEvidenceRequest(
        plan=plan,
        backend=backend,
        realization=realization,
        project_dir=tmp_path,
        environment={},
        run_store=LocalRunStore(tmp_path / "runs"),
        run_id="run-1",
        capture_selection=selection,
        clock=FixedClockProvider(measurement_time="2026-11-09T00:00:00Z"),
    )


def test_trial_measurement_runs_every_techvault_source_without_preparation(
    tmp_path, released_techvault_realization
):
    from aptl.backends.raes_evidence_acquisition import acquire_trial_evidence

    backend = _RecordingBackend()
    request = _request(
        tmp_path, released_techvault_realization, backend, _capture_selection()
    )

    result = acquire_trial_evidence(request, attempt_id="attempt-1")

    reports = {report.registration_id: report for report in result.reports}
    assert set(reports) == set(_NATIVE)
    # The sources ran through admitted operations: they were not dropped.
    assert backend.touched("aptl-suricata")
    assert backend.touched("aptl-wazuh-manager")
    # Measurement observes only: no MISP write, SQLi probe, or freshness event.
    assert backend.effects() == []
    assert not backend.touched("aptl-misp")
    assert reports[_MISP].status is CollectorStatus.SOURCE_UNAVAILABLE
    assert reports[_SQLI].status is CollectorStatus.SOURCE_UNAVAILABLE


def test_startup_hands_the_preparation_context_to_techvault_sources(
    tmp_path, released_techvault_realization
):
    from aptl.backends.raes_evidence_acquisition import acquire_native_evidence
    from aptl.backends.scenario_capture import CaptureSourceContext

    selection = _capture_selection()
    adapter = selection.contribution.runtime_adapter
    received = []

    class _Recording:
        def native_sources(self, context):
            received.append(context)
            return adapter.native_sources(context)

    selection = replace(
        selection,
        contribution=replace(selection.contribution, runtime_adapter=_Recording()),
    )
    backend = _RecordingBackend()
    request = _request(tmp_path, released_techvault_realization, backend, selection)

    acquire_native_evidence(request)

    assert len(received) == 1
    context = received[0]
    assert isinstance(context, CaptureSourceContext)
    assert context.phase is AcquisitionPhase.PREPARATION
    assert not hasattr(context, "backend") and not hasattr(context, "project_dir")
    # Preparation authority reaches the sources: the SQLi probe is sent.
    assert any("UNION" in text for text in backend.effects())
