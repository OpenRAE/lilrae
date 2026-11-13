"""The trial CLI retains measurements and keeps a false objective verdict false."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
import json
from types import SimpleNamespace

from aptl.backends.raes_evidence_acquisition import acquire_trial_evidence
from aptl.backends.raes_start_model import StartedTrialRuntime
from aptl.core.config import AptlConfig
from aptl.core.evidence.adapters.sources import CallableWindowedSource, SourceResult
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.trial_attempt import TrialAttempt
from aptl.core.trial_record import TrialRecord, seal_trial_record
from tests.trial_capture_fixture import capture_request


def test_cli_uses_one_owner_and_does_not_turn_complete_capture_into_success(tmp_path, monkeypatch):
    from aptl.cli import lab_trial
    from aptl.backends import raes_evaluator, raes_repro

    request, registration = capture_request(tmp_path)
    (tmp_path / ".env").write_text("")
    store = request.run_store
    store.create_run(request.run_id)
    store.write_json(request.run_id, "manifest.json", {"startup": "synthetic"})
    attempt = TrialAttempt(request.run_id, "attempt-1", datetime(2030, 1, 1, tzinfo=UTC))
    digest = "sha256:" + "a" * 64
    events = []
    initial = object()
    native = SimpleNamespace(bindings=(SimpleNamespace(
        implementation_selection=SimpleNamespace(participant_address="participant.behavior.red"),
        execution_binding=SimpleNamespace(timeout_seconds=600),
    ),))
    policy = object()
    snapshot = SimpleNamespace(
        evaluation_results={"evaluation.objective.red": {"passed": False}},
        proposition_truth_results={},
    )
    source = CallableWindowedSource(lambda *_: SourceResult(
        status=CollectorStatus.OK, records=[{"observed": False}]
    ))

    def observe(start, end):
        events.append("observe")
        assert (start, end) == ("2026-11-04T00:00:00Z", "2026-11-04T00:10:00Z")

    selection = replace(request.capture_selection, contribution=replace(
        request.capture_selection.contribution,
        native_registration_ids=frozenset(),
        runtime_adapter=SimpleNamespace(observe_trial_end=observe),
    ))

    class Runtime:
        def collect_evidence(self, selected, **options):
            assert selected.plan is request.plan
            assert selected.run_store is store
            assert selected.capture_selection is selection
            events.append("collect")
            return acquire_trial_evidence(
                replace(selected, clock=request.clock), **{
                    **options, "sources": {registration.registration_id: source}
                }
            )

    runtime = Runtime()
    runtime.snapshot = snapshot
    admitted = SimpleNamespace(
        bundle=SimpleNamespace(root=tmp_path, trial=SimpleNamespace(
            scenario=object(), snapshot_digest=digest, participant_configuration_results=()
        )),
        trial_capture_plan=request.plan, realization=request.realization,
        capture_selection=selection,
        target=SimpleNamespace(participant_runtime=SimpleNamespace(autonomous_execution=native)),
        execution_plan=SimpleNamespace(model=SimpleNamespace(
            behavior_specifications={"control": SimpleNamespace(autonomous_execution=policy)}
        )),
    )
    started = StartedTrialRuntime(admitted, runtime, request.backend, store, (initial,))

    @contextmanager
    def executors(*args, **options):
        assert set(options["bindings"]) == {"agents.red"}
        yield {"agents.red": object()}
        events.append("drained")

    def run(trial, **options):
        release = options["release"]
        assert release.runtime is runtime
        assert release.native is native
        assert release.policy is policy
        assert trial.episode_seconds == 600
        events.append("participants")
        return TrialRecord(
            run_id=attempt.run_id, attempt_id=attempt.attempt_id, scenario_sha256=digest,
            deadline="2030-01-01T00:00:00Z", started_at="2026-11-04T00:00:00Z",
            ended_at="2026-11-04T00:10:00Z", terminal_cause="completed", participants=(),
        )

    def evaluate(**options):
        assert options["runtime_manager"] is runtime
        assert options["target"] is admitted.target
        before, measurement = options["evidence_records"]
        assert before is initial
        assert measurement.run_ref.ref_id == request.run_id
        events.append("evaluate")

    monkeypatch.setattr(lab_trial, "admitted_participants", lambda *args: ())
    monkeypatch.setattr(lab_trial, "_launch_settings", lambda *args: None)
    monkeypatch.setattr(lab_trial, "trial_executors", executors)
    monkeypatch.setattr(lab_trial, "run_declared_trial", run)
    monkeypatch.setattr(raes_evaluator, "refresh_evidence_truth", evaluate)
    monkeypatch.setattr(raes_repro, "runtime_snapshot_record_payload", lambda value: value.evaluation_results)
    record, gaps = lab_trial._run_and_drain(tmp_path, AptlConfig(), attempt, digest, lambda text: None, started)
    assert events == ["collect", "participants", "observe", "drained", "evaluate"]
    assert gaps == ()
    assert record.outcome_status == "failed"
    seal = json.loads(seal_trial_record(store, record).read_bytes())
    assert seal["completeness"]["complete"] is True
    assert seal["outcome_status"] == "failed"
    saved = json.loads((store.get_run_path(record.run_id) / "trial/evaluation.json").read_bytes())
    assert saved["objectives"]["evaluation.objective.red"]["passed"] is False
