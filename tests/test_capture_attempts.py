"""Native results and failed reports retain the caller's attempt identity."""

from dataclasses import replace
from types import SimpleNamespace
import pytest
from tests.trial_capture_fixture import capture_request
from aptl.backends.raes_evidence_acquisition import acquire_trial_evidence
from aptl.core.evidence.adapters.sources import CallableWindowedSource, SourceResult
from aptl.core.evidence.outcomes import CollectorStatus


@pytest.mark.parametrize("available", [False, True])
def test_same_native_request_in_two_attempts_has_distinct_results(tmp_path, available):
    request, registration = capture_request(tmp_path)
    source = CallableWindowedSource(
        lambda *a: SourceResult(
            status=CollectorStatus.OK
            if available
            else CollectorStatus.SOURCE_UNAVAILABLE,
            records=[{"message": "same native bytes"}] if available else [],
        )
    )
    contribution = replace(
        request.capture_selection.contribution,
        runtime_adapter=SimpleNamespace(
            native_sources=lambda context: {registration.registration_id: source}
        ),
    )
    request = replace(
        request,
        capture_selection=replace(request.capture_selection, contribution=contribution),
    )
    results = [
        acquire_trial_evidence(request, attempt_id=attempt)
        for attempt in ("first", "second")
    ]
    for attempt, result in zip(("first", "second"), results, strict=True):
        assert result.scope.attempt_id == attempt
        report = result.reports[0]
        assert report.scope == result.scope
        assert report.scope.run_id == request.run_id
        assert report.capture_spec_id == request.plan.runtime_bindings()[0].capture_spec_id
        assert report.requirement_id == request.plan.runtime_bindings()[0].requirement_id
        if available:
            assert result.refs[0].attempt_id == attempt
            assert result.refs[0].as_reference_dict()["attempt_id"] == attempt
            assert any(
                ref.ref_id == f"attempt:{attempt}"
                for ref in result.records[0].source_refs
            )
    if available:
        assert (
            results[0].records[0].evidence_record_id
            != results[1].records[0].evidence_record_id
        )
        assert results[0].refs[0].content_uri == results[1].refs[0].content_uri
