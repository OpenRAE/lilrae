"""Selected capture offers execute through the existing acquisition path."""

from dataclasses import replace
import json
from subprocess import CompletedProcess
from types import SimpleNamespace

import pytest

from tests.trial_capture_fixture import capture_request
from aptl.backends.raes_manifest import create_aptl_manifest
from aptl.backends.scenario_runtime_hooks import AdmittedRuntimeOperations
from aptl.core.evidence.adapters.builtins import ContainerLogSource
from aptl.core.evidence.adapters.sources import CallableWindowedSource, SourceResult
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.experiment.capture_plan import admit_capture_demands
from aptl.core.experiment.capture_registry import CollectorRegistry


def test_selected_container_logs_preserve_both_streams_and_accepted_prefix():
    calls = []

    def logs(name, **kwargs):
        calls.append((name, kwargs))
        if name == "missing":
            raise OSError("private backend failure")
        return CompletedProcess([], 0, "first line\n", "second line\n")

    operations = AdmittedRuntimeOperations(
        SimpleNamespace(container_logs_capture=logs),
        [SimpleNamespace(name="soc"), SimpleNamespace(name="missing")],
    )
    result = ContainerLogSource(operations, ["soc", "missing"]).fetch(
        "2026-11-04T00:00:00Z", "2026-11-04T00:01:00Z"
    )
    assert result.status is CollectorStatus.SOURCE_UNAVAILABLE
    assert result.records == [
        {"container": "soc", "output": "first line\n", "stderr": "second line\n"},
        {"container": "missing", "status": "source-unavailable"},
    ]
    assert calls[0][1].pop("max_bytes") > 0
    assert calls[0][1] == {
        "since": "2026-11-04T00:00:00Z",
        "until": "2026-11-04T00:01:00Z",
        "timeout": 30,
    }
    with pytest.raises(ValueError, match="not-admitted"):
        operations.container_logs_capture(
            "other-trial", since="s", until="e", timeout=30
        )


def test_selected_log_files_retain_raw_records_and_disclose_truncation():
    from aptl.core.evidence.adapters.builtins import ContainerFileSource

    calls = []

    def execute(name, command, **kwargs):
        calls.append((name, command))
        return CompletedProcess(command, 0, "one\ntwo\n", "")

    operations = AdmittedRuntimeOperations(
        SimpleNamespace(container_exec=execute), [SimpleNamespace(name="soc")]
    )
    source = ContainerFileSource(
        operations,
        [("soc", "/var/log/events.json")],
        max_bytes=7,
        timestamp_of=lambda line: "2026-11-04T00:00:01Z",
    )
    result = source.fetch("2026-11-04T00:00:00Z", "2026-11-04T00:01:00Z")
    assert result.status is CollectorStatus.TRUNCATION
    assert result.records[0]["output"] == "one\ntwo"
    assert result.records[0]["path"] == "/var/log/events.json"
    assert calls == [("soc", ["head", "-c", "8", "--", "/var/log/events.json"])]


def test_observed_empty_log_file_discloses_unverified_window_coverage():
    from aptl.core.evidence.adapters.builtins import ContainerFileSource
    from aptl.core.evidence.adapters.sources import source_result_to_outcome

    source = ContainerFileSource(
        SimpleNamespace(container_exec=lambda *a, **k: CompletedProcess([], 0, "", "")),
        [("soc", "/var/log/events.json")],
        timestamp_of=lambda line: "2026-11-04T00:00:01Z",
    )
    result = source.fetch("2026-11-04T00:00:00Z", "2026-11-04T00:01:00Z")
    assert result.status is CollectorStatus.MID_RUN_LOSS
    outcome = source_result_to_outcome(result, "start", "end")
    assert outcome.status is CollectorStatus.MID_RUN_LOSS
    assert json.loads(b"".join(outcome.chunks))[0]["path"] == "/var/log/events.json"


@pytest.mark.parametrize(
    "change",
    [
        {"integrity_modes": frozenset({"chain_of_custody"})},
        {"field_selectors": ("/invented-field",)},
        {"window_kinds": frozenset({"episode"})},
        {"retention_policy_refs": frozenset({"study_lifetime"})},
    ],
)
def test_participant_registration_refuses_unsupported_manifest_claims(tmp_path, change):
    from aptl.core.evidence.participant_capture import participant_capture_registration

    request, registration = capture_request(tmp_path)
    offer = replace(
        registration.capture_offer,
        channel_kinds=frozenset({"participant-observation"}),
        scopes=frozenset({"participant"}),
    )
    assert not participant_capture_registration(
        "rpt.collector.red", offer
    ).supports_chain_of_custody
    unsupported = replace(offer, **change)
    with pytest.raises(ValueError, match="unsupported"):
        participant_capture_registration("rpt.collector.red", unsupported)


@pytest.mark.parametrize("failed", [False, True])
def test_manifest_admitted_trial_source_returns_artifacts_and_honest_status(
    tmp_path, failed
):
    from aptl.backends.raes_evidence_acquisition import acquire_trial_evidence

    request, registration = capture_request(tmp_path)
    offer = create_aptl_manifest(
        registry=request.capture_selection.registry
    ).observation.capture_offers[0]
    assert offer == registration.capture_offer
    events = []

    def fetch(start, end):
        events.append("collect")
        return SourceResult(
            status=CollectorStatus.MID_RUN_LOSS if failed else CollectorStatus.OK,
            records=[{"message": "actual source log", "api_key": "private-canary"}],
        )

    result = acquire_trial_evidence(
        request,
        attempt_id="attempt-1",
        sources={registration.registration_id: CallableWindowedSource(fetch)},
        trial_body=lambda: events.append("participant"),
    )
    assert events == ["participant", "collect"]
    assert result.reports[0].status is (
        CollectorStatus.MID_RUN_LOSS if failed else CollectorStatus.OK
    )
    assert len(result.refs) == 1
    from aptl.utils.pathsafe import read_contained_nofollow

    content = read_contained_nofollow(
        request.run_store.get_run_path("run-1"), result.refs[0].content_uri
    )
    assert json.loads(content) == [
        {"message": "actual source log", "api_key": "[REDACTED]"}
    ]
    assert (
        "mid-run" in (result.records[0].raw_content.loss_disclosure or "")
    ) is failed


def test_missing_or_undeclared_trial_sources_do_not_start_participants(tmp_path):
    from aptl.backends.raes_evidence_acquisition import acquire_trial_evidence

    request, registration = capture_request(tmp_path)
    effects = []
    result = acquire_trial_evidence(
        request, attempt_id="attempt-1", trial_body=lambda: effects.append(True)
    )
    assert not effects
    assert not result.refs
    assert result.diagnostics
    source = CallableWindowedSource(lambda *a: SourceResult(status=CollectorStatus.OK))
    with pytest.raises(ValueError, match="unknown collector registration"):
        acquire_trial_evidence(
            request,
            attempt_id="attempt-1",
            sources={"rpt.unknown": source},
            trial_body=lambda: effects.append(True),
        )
    assert not effects


@pytest.mark.parametrize("native_failure", [None, RuntimeError, ValueError, TypeError])
def test_both_participants_and_adapter_logs_share_the_advertised_trial_path(
    tmp_path, native_failure
):
    from aptl.backends.raes_evidence_acquisition import acquire_trial_evidence
    from aptl.core.evidence.participant_capture import (
        ParticipantCaptureArchive,
        participant_capture_registration,
    )
    from aptl.core.evidence.protocol import RunScope
    from tests.test_participant_capture import _grant
    from tests.test_lilrae_participant_configuration import configuration
    from tests.trial_capture_fixture import run_managed_capture
    from aptl.utils.pathsafe import read_contained_nofollow

    request, logs = capture_request(tmp_path)
    registrations = [logs]
    demands = [request.plan.bindings[0].demand]
    for role in ("red", "blue"):
        offer = replace(
            logs.capture_offer,
            offer_id=f"rpt.{role}",
            source_refs=frozenset({f"participant.behavior.{role}"}),
            scope_refs=frozenset({f"participant.behavior.{role}"}),
            scopes=frozenset({"participant"}),
            channel_kinds=frozenset({"participant-observation"}),
        )
        registrations.append(
            participant_capture_registration(f"rpt.collector.{role}", offer)
        )
        demands.append(
            replace(
                demands[0],
                demand_id=f"{role}-agent-trace",
                address=f"evidence_requirements.{role}-agent-trace",
                source_refs=(f"participant.behavior.{role}",),
                scope_refs=(f"participant.behavior.{role}",),
                scopes=("participant",),
                channel_kinds=("participant-observation",),
            )
        )
    registry = CollectorRegistry(tuple(registrations))
    plan = admit_capture_demands(
        tuple(demands), source_identity=request.plan.source_identity, registry=registry
    )
    archives = {}
    for role in ("red", "blue"):
        binding = next(
            b
            for b in plan.runtime_bindings()
            if b.registration_id == f"rpt.collector.{role}"
        )
        grant = replace(
            _grant(),
            binding=binding,
            scope=RunScope(request.run_id, plan.plan_id, "attempt-1"),
            participant_address=f"participant.behavior.{role}",
            configuration_digest=configuration(role=role)[1].configuration_digest,
        )
        archives[binding.registration_id] = ParticipantCaptureArchive(
            request.run_store, grant
        )

    def native_sources(context):
        return {logs.registration_id: ContainerLogSource(context.operations, ["soc"])}

    contribution = replace(
        request.capture_selection.contribution,
        registrations=tuple(registrations),
        runtime_adapter=SimpleNamespace(native_sources=native_sources),
    )
    request = replace(
        request,
        plan=plan,
        capture_selection=replace(
            request.capture_selection, registry=registry, contribution=contribution
        ),
        backend=SimpleNamespace(
            container_logs_capture=lambda *a, **k: CompletedProcess(
                [], 0, "alert\n", ""
            )
        ),
        realization=SimpleNamespace(
            nodes=(SimpleNamespace(name="soc"),), generated_artifacts=()
        ),
    )
    assert len(create_aptl_manifest(registry=registry).observation.capture_offers) == 3

    def participants():
        for role in ("red", "blue"):
            run_managed_capture(tmp_path, archives[f"rpt.collector.{role}"], role)

    if native_failure:
        participants()

        def unavailable(context):
            raise native_failure("private source initialization detail")

        request = replace(
            request,
            capture_selection=replace(
                request.capture_selection,
                contribution=replace(
                    contribution,
                    runtime_adapter=SimpleNamespace(native_sources=unavailable),
                ),
            ),
        )
    result = acquire_trial_evidence(
        request,
        attempt_id="attempt-1",
        sources=archives,
        trial_body=None if native_failure else participants,
    )
    assert len(result.refs) == (2 if native_failure else 3)
    reports = {report.registration_id: report for report in result.reports}
    assert reports[logs.registration_id].status is (
        CollectorStatus.SOURCE_UNAVAILABLE if native_failure else CollectorStatus.OK
    )
    assert all(
        reports[f"rpt.collector.{role}"].status is CollectorStatus.OK
        for role in ("red", "blue")
    )
    payloads = {
        ref.registration_id: json.loads(
            read_contained_nofollow(
                request.run_store.get_run_path(request.run_id), ref.content_uri
            )
        )
        for ref in result.refs
    }
    if not native_failure:
        assert payloads[logs.registration_id][0]["output"] == "alert\n"
    for role in ("red", "blue"):
        row = payloads[f"rpt.collector.{role}"][0]
        assert row["participant_address"] == f"participant.behavior.{role}"
        assert row["attempt_id"] == "attempt-1"
        assert row["totals"]["input_tokens"] == 12
        invocation = row["invocations"][0]
        assert invocation["prompt_delivery"]["provider_request_observed"]
        assert invocation["cli_events"][0]["part"]["text"] == f"{role} observation"
        assert (
            invocation["cli_events"][1]["part"]["text"] == f"{role} returned reasoning"
        )
        call = invocation["calls"][0]
        assert (
            call["reasoning_tokens"],
            call["cache_read_tokens"],
            call["cache_write_tokens"],
        ) == (2, 5, 4)
        assert (
            row["action_counts"]["dispatched"] == row["action_counts"]["succeeded"] == 1
        )
        assert row["tool_events"][0]["arguments"] == {"command": "id"}
        assert f"{role} tool result" in json.dumps(row["tool_events"])
        assert "private-credential" not in json.dumps(row)


def test_capture_rejects_a_participant_source_from_another_attempt(tmp_path):
    from aptl.backends.raes_evidence_acquisition import acquire_trial_evidence
    from aptl.core.evidence.participant_capture import ParticipantCaptureArchive
    from aptl.core.evidence.protocol import RunScope
    from tests.test_participant_capture import _grant

    request, registration = capture_request(tmp_path)
    archive = ParticipantCaptureArchive(
        request.run_store,
        replace(
            _grant(),
            binding=request.plan.runtime_bindings()[0],
            scope=RunScope(request.run_id, request.plan.plan_id, "other-attempt"),
        ),
    )
    effects = []
    with pytest.raises(ValueError, match="another trial"):
        acquire_trial_evidence(
            request,
            attempt_id="attempt-1",
            sources={registration.registration_id: archive},
            trial_body=lambda: effects.append(True),
        )
    assert not effects


def test_changed_manifest_or_failed_source_factory_prevents_trial_effects(tmp_path):
    from aptl.backends.raes_evidence_acquisition import acquire_trial_evidence

    request, registration = capture_request(tmp_path)
    changed = replace(
        request.capture_selection,
        registry=CollectorRegistry(
            (replace(registration, implementation_version="2.0.0"),)
        ),
    )
    effects = []
    changed_request = replace(request, capture_selection=changed)
    with pytest.raises(ValueError, match="changed after admission"):
        acquire_trial_evidence(
            changed_request,
            attempt_id="attempt-1",
            trial_body=lambda: effects.append(True),
        )

    def failed(context):
        raise RuntimeError("private source diagnostics")

    contribution = replace(
        request.capture_selection.contribution,
        runtime_adapter=SimpleNamespace(native_sources=failed),
    )
    result = acquire_trial_evidence(
        replace(
            request,
            capture_selection=replace(
                request.capture_selection, contribution=contribution
            ),
        ),
        attempt_id="attempt-1",
        trial_body=lambda: effects.append(True),
    )
    assert result.diagnostics
    assert not effects


def test_runtime_capture_entry_point_uses_its_manifest_and_owned_backend(tmp_path):
    from aptl.backends.raes_runtime import AptlRuntimeManager
    from aptl.backends._raes_runtime_target import create_aptl_runtime_target
    from aptl.backends._raes_runtime_target_options import RuntimeTargetOptions
    from aptl.core.config import AptlConfig
    from aptl.core.scenario_bundle import project_tree_bundle

    request, registration = capture_request(tmp_path)
    request = replace(request, window=("2026-11-04T00:00:00Z", "2026-11-04T00:01:00Z"))
    scenario = tmp_path / "trial.sdl.yaml"
    scenario.write_text("name: capture\nnodes: {}\n")
    target = create_aptl_runtime_target(
        project_dir=tmp_path,
        config=AptlConfig(),
        backend=request.backend,
        bundle=project_tree_bundle(tmp_path, scenario),
        options=RuntimeTargetOptions(
            capture_selection=request.capture_selection, capture_plan=request.plan
        ),
    )
    with AptlRuntimeManager(target, run_scope="run:run-1") as runtime:
        source = CallableWindowedSource(
            lambda *a: SourceResult(
                status=CollectorStatus.OK, records=[{"log": "retained"}]
            )
        )
        result = runtime.collect_evidence(
            request,
            attempt_id="attempt-1",
            sources={registration.registration_id: source},
        )
        assert len(result.refs) == 1
        assert result.reports[0].status is CollectorStatus.OK
        other_request = replace(request, run_id="other-run")
        with pytest.raises(ValueError, match="runtime owner"):
            runtime.collect_evidence(other_request, attempt_id="attempt-1")


def test_capture_phase_retains_accepted_data_with_requested_window_when_peer_is_missing(
    tmp_path,
):
    from aptl.backends.raes_evidence_acquisition import acquire_trial_evidence

    request, registration = capture_request(tmp_path)
    missing = replace(registration, registration_id="rpt.missing")
    registry = CollectorRegistry((registration, missing))
    binding = replace(
        request.plan.bindings[0],
        registration_id=missing.registration_id,
        effective_config_digest=missing.effective_config_digest(),
        demand=replace(request.plan.bindings[0].demand, demand_id="missing"),
    )
    plan = replace(request.plan, bindings=(*request.plan.bindings, binding))
    request = replace(
        request,
        plan=plan,
        window=("2026-11-04T00:00:00Z", "2026-11-04T00:01:00Z"),
        capture_selection=replace(request.capture_selection, registry=registry),
    )
    windows = []

    def fetch(start, end):
        windows.append((start, end))
        return SourceResult(status=CollectorStatus.OK, records=[{"actual": "retained"}])

    result = acquire_trial_evidence(
        request,
        attempt_id="attempt-1",
        sources={registration.registration_id: CallableWindowedSource(fetch)},
    )
    assert windows == [request.window]
    assert len(result.refs) == 1
    assert {r.status for r in result.reports} == {
        CollectorStatus.OK,
        CollectorStatus.SOURCE_UNAVAILABLE,
    }
