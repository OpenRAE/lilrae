"""Lost tool observations cannot become a successful zero-action capture."""

from dataclasses import replace
from threading import Event
import json
import pytest
from aptl.backends.participant_tools.session import LilraeToolSession
from aptl.core.evidence.participant_capture import ParticipantCaptureArchive
from aptl.core.evidence.adapters.sources import WindowedQueryCollector
from aptl.core.evidence.coordinator import acquire_evidence
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.experiment.capture_registry import CaptureLimits
from aptl.core.runstore import LocalRunStore
from aptl.workbench.process import AgentExecutionError
from tests.test_participant_capture import _grant, _payload
from tests.test_lilrae_participant_tools import port, binding
from tests.test_evidence_coordinator import _CLOCK


@pytest.mark.parametrize(
    "lost", [{"dispatched"}, {"dispatched", "unsettled"}, {"unsettled"}]
)
def test_lost_observation_writes_keep_model_artifact_and_disclose_uncertain_counts(
    tmp_path, monkeypatch, lost
):
    native = port()
    grant = replace(
        _grant(),
        participant_address=native.participant_address,
        binding=replace(_grant().binding, limits=CaptureLimits(32768, 100, 60)),
    )
    store = LocalRunStore(tmp_path / "runs")
    archive = ParticipantCaptureArchive(store, grant)
    real_write = store.create_run_json_once

    def write(run, path, payload):
        if "participant-tool-capture" in path and payload["phase"] in lost:
            raise OSError("private write failure")
        return real_write(run, path, payload)

    monkeypatch.setattr(store, "create_run_json_once", write)
    session = LilraeToolSession(
        native, (binding(),), Event(), evidence_sink=archive.record_tool_event
    )

    def fail(args):
        raise TimeoutError("private native failure")

    with pytest.raises(AgentExecutionError):
        session.invoke("aptl-red", "kali_run_command", {"command": "id"}, "call", fail)
    archive.record(_payload())
    # A fresh source must also see the persisted observation-loss marker.
    resumed = ParticipantCaptureArchive(store, grant)
    collector = WindowedQueryCollector(grant.binding.registration_id, resumed)
    result = acquire_evidence(
        bindings=[grant.binding],
        collectors={grant.binding.registration_id: collector},
        run_store=store,
        scope=grant.scope,
        clock=_CLOCK,
    )
    assert result.reports[0].status is CollectorStatus.MID_RUN_LOSS
    retained = json.loads(
        (
            store.get_run_path(grant.scope.run_id) / result.refs[0].content_uri
        ).read_bytes()
    )[0]
    assert retained["invocations"][0]["calls"][0]["input_tokens"] == 12
    assert retained["tool_capture_complete"] is False
    assert retained["action_counts"]["dispatched"] is None
    assert retained["action_counts"]["known_counts"]["admitted"] == 1
    assert "private write failure" not in json.dumps(retained)
