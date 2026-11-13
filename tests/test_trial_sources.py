"""Original chat usage and bounded audit data reach admitted capture records."""

from dataclasses import replace
import json

from aptl.backends.raes_evidence_acquisition import acquire_trial_evidence
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.evidence.trial_sources import (
    SESSION_REGISTRATION,
    host_audit_source,
    participant_session_source,
    trial_capture_registrations,
)
from aptl.core.experiment.capture_plan import admit_capture_demands
from aptl.core.experiment.capture_registry import CollectorRegistry
from tests.trial_capture_fixture import capture_request
import pytest


@pytest.mark.parametrize(
    "participants", [("agents.operator",), ("agents.red", "agents.blue")]
)
def test_native_usage_and_scenario_credentials_survive_acquisition(
    tmp_path, participants
):
    request, _ = capture_request(tmp_path)
    registration, _ = trial_capture_registrations(frozenset({"nodes.soc"}))
    demand = replace(
        request.plan.bindings[0].demand,
        demand_id="participant-sessions",
        capture_kind="log",
        artifact_roles=("lilrae.participant-sessions",),
        channel_refs=("lilrae.participant-sessions",),
        sensitivity="plain",
    )
    registry = CollectorRegistry((registration,))
    plan = admit_capture_demands(
        (demand,), source_identity="test-native-export", registry=registry
    )
    request = replace(
        request,
        plan=plan,
        capture_selection=replace(
            request.capture_selection,
            registry=registry,
            contribution=replace(
                request.capture_selection.contribution,
                registrations=(registration,),
                native_registration_ids=frozenset(),
            ),
        ),
    )
    sessions = {
        address: {
            "messages": [
                {
                    "tokens": {"input": 17, "output": 3},
                    "cost": 0.002,
                    "api_key": "private-test-credential",
                }
            ]
        }
        for address in participants
    }
    result = acquire_trial_evidence(
        request,
        attempt_id="attempt-1",
        sources={
            SESSION_REGISTRATION: participant_session_source(sessions, participants),
        },
    )
    assert result.reports[0].status == CollectorStatus.OK
    content = (
        request.run_store.get_run_path(request.run_id) / result.refs[0].content_uri
    ).read_bytes()
    assert b"private-test-credential" in content
    payload = json.loads(content)
    assert len(payload) == len(participants)
    for item in payload:
        message = item["native_export"]["messages"][0]
        assert message["tokens"] == {"input": 17, "output": 3}
        assert message["cost"] == 0.002


def test_missing_participant_export_is_loss_and_keeps_the_available_peer():
    source = participant_session_source({"red": {"messages": []}}, ("red", "blue"))
    result = source.fetch("2026-11-12T00:00:00Z", "2026-11-12T00:10:00Z")
    assert result.status == CollectorStatus.MID_RUN_LOSS
    assert [row["participant"] for row in result.records] == ["red"]


def test_audit_source_keeps_only_the_episode_and_detects_missing_logs(tmp_path):
    source = host_audit_source(tmp_path)
    assert (
        source.fetch("2026-11-12T00:00:00Z", "2026-11-12T00:00:01Z").status
        == CollectorStatus.SOURCE_UNAVAILABLE
    )
    (tmp_path / "audit.log").write_bytes(
        b"type=EXECVE msg=audit(1794441599.001:1): old\n"
        b"type=EXECVE msg=audit(1794441600.001:2): current\n"
        b"type=EXECVE msg=audit(1794441602.001:3): later\n"
    )
    result = source.fetch("2026-11-12T00:00:00Z", "2026-11-12T00:00:01Z")
    assert result.status == CollectorStatus.OK
    assert "current" in result.records[0]["audit_log"]
    assert "old" not in result.records[0]["audit_log"]
    assert "later" not in result.records[0]["audit_log"]


def test_measurement_sources_are_not_authorized_for_startup_preparation(tmp_path):
    from types import SimpleNamespace
    from aptl.backends.scenario_capture import family_capture_sources
    from aptl.core.evidence.outcomes import AcquisitionPhase

    request, registration = capture_request(tmp_path)
    source = participant_session_source({}, ())
    contribution = replace(
        request.capture_selection.contribution,
        native_registration_ids=frozenset(),
        measurement_registration_ids=frozenset({registration.registration_id}),
        runtime_adapter=SimpleNamespace(
            native_sources=lambda _: {registration.registration_id: source}
        ),
    )
    request = replace(
        request,
        capture_selection=replace(request.capture_selection, contribution=contribution),
    )
    assert family_capture_sources(request) == {registration.registration_id: source}
    with pytest.raises(ValueError, match="family-capture-sources-invalid"):
        family_capture_sources(request, phase=AcquisitionPhase.PREPARATION)
