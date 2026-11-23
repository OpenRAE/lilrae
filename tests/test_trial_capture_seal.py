"""A trial seal requires its admitted captures and their original bytes."""

import json
from dataclasses import replace

import pytest

from aptl.backends.raes_evidence_acquisition import acquire_trial_evidence
from aptl.core.evidence.adapters.sources import CallableWindowedSource, SourceResult
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.trial_record import TrialRecord, retain_trial_capture, seal_trial_record
from tests.trial_capture_fixture import capture_request


def _captured(tmp_path, *, unavailable=False):
    request, registration = capture_request(tmp_path)
    request = replace(
        request,
        capture_selection=replace(
            request.capture_selection,
            contribution=replace(
                request.capture_selection.contribution,
                native_registration_ids=frozenset(),
            ),
        ),
    )
    source = CallableWindowedSource(
        lambda *_: SourceResult(
            status=CollectorStatus.SOURCE_UNAVAILABLE
            if unavailable
            else CollectorStatus.OK,
            records=[] if unavailable else [{"observation": "retained", "password": "scenario-fixture"}],
        )
    )
    result = acquire_trial_evidence(
        request, attempt_id="attempt-1", sources={registration.registration_id: source}
    )
    record = TrialRecord(
        run_id=request.run_id,
        attempt_id="attempt-1",
        scenario_sha256="sha256:" + "a" * 64,
        deadline="2026-11-04T00:15:00Z",
        started_at="2026-11-04T00:00:00Z",
        ended_at="2026-11-04T00:10:00Z",
        terminal_cause="completed",
        participants=(),
    )
    record = retain_trial_capture(request.run_store, record, request.plan, result)
    request.run_store.write_json(
        record.run_id, "manifest.json", {"startup": "synthetic"}
    )
    return request, result, record


def _seal(request, record):
    return json.loads(seal_trial_record(request.run_store, record).read_bytes())


def test_only_the_admitted_capture_set_defines_data_completeness(tmp_path):
    request, _, record = _captured(tmp_path)
    seal = _seal(request, record.model_copy(update={"outcome_status": "inconclusive"}))
    assert seal["completeness"]["complete"] is True
    assert seal["outcome_status"] == "inconclusive"
    assert not (request.run_store.get_run_path(record.run_id) / "trial/audit").exists()


@pytest.mark.parametrize("failure", ["source", "report", "blob", "attempt", "plan"])
def test_missing_or_changed_required_evidence_cannot_seal_as_complete(
    tmp_path, failure
):
    request, result, record = _captured(tmp_path, unavailable=failure == "source")
    store = request.run_store
    root = store.get_run_path(record.run_id)
    if failure in {"report", "attempt"}:
        capture = json.loads((root / "trial/capture.json").read_bytes())
        if failure == "report":
            capture["reports"] = []
        else:
            capture["attempt_id"] = "another-attempt"
        store.write_json(record.run_id, "trial/capture.json", capture)
    elif failure == "blob":
        store.write_file(record.run_id, result.refs[0].content_uri, b"changed")
    elif failure == "plan":
        relative = f"evidence/capture-plans/{record.capture_plan_id}.json"
        plan = json.loads((root / relative).read_bytes())
        plan["bindings"] = []
        store.write_json(record.run_id, relative, plan)
    seal = _seal(request, record)
    assert seal["completeness"]["complete"] is False
    assert any(
        item["code"] == "required-data-missing"
        for item in seal["completeness"]["limitations"]
    )


def test_a_fixed_file_list_cannot_replace_the_admitted_capture_plan(tmp_path):
    request, _, record = _captured(tmp_path)
    store = request.run_store
    store.write_json(record.run_id, "trial/audit/status.json", {"status": "captured"})
    store.write_json(record.run_id, "trial/soc/manifest.json", {})
    seal = _seal(request, record.model_copy(update={"capture_plan_id": None}))
    assert seal["completeness"]["complete"] is False


def test_final_results_and_seal_preserve_scenario_content(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from raes_contracts.runtime_state import RuntimeSnapshot
    from aptl.backends import raes_evaluator
    from aptl.cli.lab_trial import _evaluate_trial

    request, capture, record = _captured(tmp_path)
    truths = {"evaluation.assertion.demo-credentials-present": {"assertion_outcome": "false"}}
    snapshot = RuntimeSnapshot(
        evaluation_results={"evaluation.objective.demo": {"passed": False}},
        proposition_truth_results=truths,
    )
    # Resume at the completed native evaluation; exercise the actual output writer.
    monkeypatch.setattr(raes_evaluator, "refresh_evidence_truth", lambda **kwargs: None)
    started = SimpleNamespace(
        admitted=SimpleNamespace(target=None, execution_plan=None),
        runtime=SimpleNamespace(snapshot=snapshot),
        initial_evidence=(),
    )
    status = _evaluate_trial(started, request.run_store, record.run_id, capture)
    root = request.run_store.get_run_path(record.run_id)
    assert status == "failed"
    assert json.loads((root / "trial/evaluation.json").read_bytes())["proposition_truth_results"] == truths
    assert json.loads((root / "trial/evaluated-runtime.json").read_bytes())["snapshot"]["proposition_truth_results"] == truths
    captured = json.loads((root / capture.refs[0].content_uri).read_bytes())
    assert captured == [{"observation": "retained", "password": "scenario-fixture"}]
    seal = _seal(request, record.model_copy(update={"outcome_status": status}))
    assert seal["completeness"]["complete"] is True
    assert seal["outcome_status"] == "failed"
