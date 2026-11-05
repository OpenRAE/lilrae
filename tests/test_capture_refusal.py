"""Malformed collector declarations are refused before trial effects."""

from dataclasses import replace
from types import SimpleNamespace
import pytest
from tests.trial_capture_fixture import capture_request
from aptl.core.evidence.adapters.sources import CallableWindowedSource, SourceResult
from aptl.core.evidence.outcomes import CollectorStatus


@pytest.mark.parametrize(
    "native", [{"undeclared": object()}, {"rpt.collector.fixture": object()}]
)
def test_invalid_native_mapping_refuses_effects_even_with_supplied_sources(
    tmp_path, native
):
    from aptl.backends.raes_evidence_acquisition import acquire_trial_evidence

    request, registration = capture_request(tmp_path)
    contribution = replace(
        request.capture_selection.contribution,
        runtime_adapter=SimpleNamespace(native_sources=lambda context: native),
    )
    request = replace(
        request,
        capture_selection=replace(request.capture_selection, contribution=contribution),
    )
    effects = []
    source = CallableWindowedSource(lambda *a: SourceResult(status=CollectorStatus.OK))
    with pytest.raises(ValueError, match="family-capture-sources-invalid"):
        acquire_trial_evidence(
            request,
            attempt_id="attempt-1",
            sources={registration.registration_id: source},
            trial_body=lambda: effects.append(True),
        )
    assert not effects


def test_invalid_supplied_source_refuses_before_trial(tmp_path):
    from aptl.backends.raes_evidence_acquisition import acquire_trial_evidence

    request, registration = capture_request(tmp_path)
    effects = []
    with pytest.raises(ValueError, match="source interface"):
        acquire_trial_evidence(
            request,
            attempt_id="attempt-1",
            sources={registration.registration_id: object()},
            trial_body=lambda: effects.append(True),
        )
    assert not effects
