"""Native acquisition phase boundary (issue #1689).

These tests drive the core phase seam: the phase vocabulary, the frozen
context field and its permission, the threading through the source-context
owners, and the two acquisition callers.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from aptl.core.evidence.adapters.sources import SourceResult
from aptl.core.evidence.outcomes import (
    AcquisitionPhase,
    CollectorStatus,
    PREPARATION_PHASES,
)


class _PhaseSource:
    """A windowed source that performs its preparation only when permitted."""

    def __init__(self, may_prepare: bool) -> None:
        self._may_prepare = may_prepare
        self.prepared = False

    def fetch(self, start_iso: str, end_iso: str) -> SourceResult:
        if self._may_prepare:
            self.prepared = True
            return SourceResult(
                status=CollectorStatus.OK,
                records=[{"public_fact": "observed"}],
                observer_effect="preparation stimulus sent",
            )
        return SourceResult(
            status=CollectorStatus.OK, records=[{"public_fact": "observed"}]
        )


class _RecordingAdapter:
    """A capture runtime adapter that records the phase it receives."""

    def __init__(self) -> None:
        self.seen_phase: AcquisitionPhase | None = None
        self.source: _PhaseSource | None = None

    def native_sources(self, context: object) -> dict[str, object]:
        self.seen_phase = context.phase
        self.source = _PhaseSource(context.may_prepare)
        return {"example.events": self.source}


def _fake_request(tmp_path, runtime_adapter):
    return SimpleNamespace(
        realization=SimpleNamespace(nodes=(), generated_artifacts=()),
        backend=object(),
        project_dir=tmp_path,
        environment={},
        capture_selection=SimpleNamespace(
            contribution=SimpleNamespace(
                runtime_adapter=runtime_adapter,
                native_registration_ids=frozenset({"example.events"}),
                runtime_environment_keys=(),
                generated_output_refs=(),
            ),
            context=SimpleNamespace(trial=None),
        ),
    )


def test_only_preparation_is_in_the_preparation_allowlist():
    assert AcquisitionPhase.PREPARATION in PREPARATION_PHASES
    assert AcquisitionPhase.MEASUREMENT not in PREPARATION_PHASES


def test_context_defaults_to_measurement_and_blocks_preparation():
    from aptl.backends.scenario_capture import CaptureSourceContext

    ctx = CaptureSourceContext(
        operations=object(), realization=object(), environment={}
    )
    assert ctx.phase is AcquisitionPhase.MEASUREMENT
    assert ctx.may_prepare is False


def test_preparation_context_permits_preparation():
    from aptl.backends.scenario_capture import CaptureSourceContext

    ctx = CaptureSourceContext(
        operations=object(),
        realization=object(),
        environment={},
        phase=AcquisitionPhase.PREPARATION,
    )
    assert ctx.may_prepare is True


def test_malformed_phase_is_rejected_before_use():
    from aptl.backends.scenario_capture import CaptureSourceContext

    with pytest.raises(ValueError, match="capture-source-phase-invalid"):
        CaptureSourceContext(
            operations=object(),
            realization=object(),
            environment={},
            phase="preparation",
        )


def test_capture_source_context_carries_the_selected_phase(tmp_path):
    from aptl.backends.scenario_capture import capture_source_context

    request = _fake_request(tmp_path, _RecordingAdapter())
    ctx = capture_source_context(request, phase=AcquisitionPhase.PREPARATION)
    assert ctx.phase is AcquisitionPhase.PREPARATION
    assert ctx.may_prepare is True


def test_family_capture_sources_threads_phase_to_the_adapter(tmp_path):
    from aptl.backends.scenario_capture import family_capture_sources

    adapter = _RecordingAdapter()
    sources = family_capture_sources(
        _fake_request(tmp_path, adapter), phase=AcquisitionPhase.PREPARATION
    )
    assert adapter.seen_phase is AcquisitionPhase.PREPARATION
    assert "example.events" in sources


def test_family_capture_sources_defaults_to_measurement(tmp_path):
    from aptl.backends.scenario_capture import family_capture_sources

    adapter = _RecordingAdapter()
    family_capture_sources(_fake_request(tmp_path, adapter))
    assert adapter.seen_phase is AcquisitionPhase.MEASUREMENT


def test_measurement_source_does_not_prepare(tmp_path):
    from aptl.backends.scenario_capture import family_capture_sources

    adapter = _RecordingAdapter()
    sources = family_capture_sources(
        _fake_request(tmp_path, adapter), phase=AcquisitionPhase.MEASUREMENT
    )
    result = sources["example.events"].fetch(
        "2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z"
    )
    assert adapter.source.prepared is False
    assert result.observer_effect is None


def test_preparation_source_prepares(tmp_path):
    from aptl.backends.scenario_capture import family_capture_sources

    adapter = _RecordingAdapter()
    sources = family_capture_sources(
        _fake_request(tmp_path, adapter), phase=AcquisitionPhase.PREPARATION
    )
    result = sources["example.events"].fetch(
        "2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z"
    )
    assert adapter.source.prepared is True
    assert result.observer_effect == "preparation stimulus sent"


def _native_request(
    tmp_path, *, trial, runtime_adapter, native_ids=frozenset({"example.events"})
):
    from aptl.backends.raes_evidence_acquisition import NativeEvidenceRequest
    from aptl.core.runstore import LocalRunStore

    plan = SimpleNamespace(
        plan_id="capture-plan-test",
        canonical_bytes=b'{"schema_version":"aptl-capture-plan/v1"}',
        runtime_bindings=lambda: (),
    )
    selection = SimpleNamespace(
        contribution=SimpleNamespace(
            runtime_adapter=runtime_adapter,
            native_registration_ids=native_ids,
            runtime_environment_keys=(),
            generated_output_refs=(),
        ),
        context=SimpleNamespace(trial=trial),
        registry=SimpleNamespace(registrations=()),
    )
    return NativeEvidenceRequest(
        plan=plan,
        backend=object(),
        realization=SimpleNamespace(nodes=(), generated_artifacts=()),
        project_dir=tmp_path,
        environment={},
        run_store=LocalRunStore(tmp_path / "runs"),
        run_id="run-1",
        capture_selection=selection,
    )


def _record_phase(monkeypatch):
    import aptl.backends.scenario_capture as sc

    recorded = {}

    def fake(request, *, establish_enrollment=False, phase):
        recorded["phase"] = phase
        return {}

    monkeypatch.setattr(sc, "family_capture_sources", fake)
    return recorded


def test_acquire_native_evidence_selects_preparation(tmp_path, monkeypatch):
    from aptl.backends import raes_evidence_acquisition as acquisition

    recorded = _record_phase(monkeypatch)
    trial = SimpleNamespace(
        identity=lambda: {"run_id": "run-1", "plan_entry_id": "entry-1"}
    )
    request = _native_request(tmp_path, trial=trial, runtime_adapter=_RecordingAdapter())

    acquisition.acquire_native_evidence(request)

    assert recorded["phase"] is AcquisitionPhase.PREPARATION


def test_acquire_native_evidence_selects_preparation_without_a_trial(
    tmp_path, monkeypatch
):
    from aptl.backends import raes_evidence_acquisition as acquisition

    recorded = _record_phase(monkeypatch)
    request = _native_request(tmp_path, trial=None, runtime_adapter=_RecordingAdapter())

    acquisition.acquire_native_evidence(request)

    assert recorded["phase"] is AcquisitionPhase.PREPARATION


@pytest.mark.parametrize(
    "trial",
    [
        None,
        SimpleNamespace(
            identity=lambda: {"run_id": "run-1", "plan_entry_id": "entry-1"}
        ),
    ],
)
def test_an_adapter_without_declared_native_sources_is_not_invoked(
    tmp_path, monkeypatch, trial
):
    from aptl.backends import raes_evidence_acquisition as acquisition

    recorded = _record_phase(monkeypatch)
    adapter = _RecordingAdapter()
    request = _native_request(
        tmp_path, trial=trial, runtime_adapter=adapter, native_ids=frozenset()
    )

    acquisition.acquire_native_evidence(request)
    acquisition.acquire_trial_evidence(
        request, attempt_id="attempt-1", trial_body=lambda: None
    )

    assert recorded == {}
    assert adapter.seen_phase is None


def test_acquire_trial_evidence_selects_measurement(tmp_path, monkeypatch):
    from aptl.backends import raes_evidence_acquisition as acquisition

    recorded = _record_phase(monkeypatch)
    request = _native_request(tmp_path, trial=None, runtime_adapter=object())

    acquisition.acquire_trial_evidence(
        request, attempt_id="attempt-1", trial_body=lambda: None
    )

    assert recorded["phase"] is AcquisitionPhase.MEASUREMENT


# --- Retention (criterion 3) ---


def test_to_outcome_retains_observer_effect_on_content_free_failure():
    from aptl.core.evidence.adapters.sources import _to_outcome

    result = SourceResult(
        status=CollectorStatus.CLOCK_SKEW,
        observer_effect="probe sent",
        source_pipeline={"source_refs": [{"ref_kind": "other", "ref_id": "x"}]},
    )
    outcome = _to_outcome(result, "2026-01-01T00:00:00Z", "2026-01-01T00:00:05Z")
    assert outcome.status is CollectorStatus.CLOCK_SKEW
    assert outcome.observer_effect == "probe sent"
    assert outcome.source_pipeline == {
        "source_refs": [{"ref_kind": "other", "ref_id": "x"}]
    }


def test_record_identity_separates_phases(tmp_path):
    from aptl.core.evidence.records import derive_evidence_record_id

    request, _ = _trial_request(tmp_path)
    binding = request.plan.runtime_bindings()[0]
    shared = dict(
        run_id="run-1",
        planned_trial_id="t",
        binding=binding,
        content_digest="sha256:" + "ab" * 32,
    )
    prep = derive_evidence_record_id(**shared, phase=AcquisitionPhase.PREPARATION)
    meas = derive_evidence_record_id(**shared, phase=AcquisitionPhase.MEASUREMENT)
    base = derive_evidence_record_id(**shared)
    assert len({prep, meas, base}) == 3


def _trial_request(tmp_path):
    from tests.trial_capture_fixture import capture_request

    return capture_request(tmp_path)


def _run_trial_with_source(tmp_path, result):
    from aptl.backends.raes_evidence_acquisition import acquire_trial_evidence
    from aptl.core.evidence.adapters.sources import CallableWindowedSource

    request, registration = _trial_request(tmp_path)
    return acquire_trial_evidence(
        request,
        attempt_id="attempt-1",
        sources={registration.registration_id: CallableWindowedSource(lambda *_: result)},
        trial_body=lambda: None,
    )


def _record_source_refs(record):
    return {(ref.ref_kind, ref.ref_id) for ref in record.source_refs}


def test_measurement_record_carries_phase_and_observer_effect(tmp_path):
    result = _run_trial_with_source(
        tmp_path,
        SourceResult(
            status=CollectorStatus.OK,
            records=[{"m": "ok"}],
            observer_effect="probe sent",
        ),
    )
    assert len(result.records) == 1
    refs = _record_source_refs(result.records[0])
    assert ("other", "acquisition-phase:measurement") in refs
    assert ("other", "observer-effect:probe sent") in refs


def test_content_free_failure_with_observer_effect_is_retained(tmp_path):
    result = _run_trial_with_source(
        tmp_path,
        SourceResult(
            status=CollectorStatus.MID_RUN_LOSS, observer_effect="probe sent"
        ),
    )
    assert len(result.records) == 1
    refs = _record_source_refs(result.records[0])
    assert ("other", "acquisition-phase:measurement") in refs
    assert ("other", "observer-effect:probe sent") in refs


def _run_native_with_source(tmp_path, result):
    from dataclasses import replace as dc_replace

    from aptl.backends.raes_evidence_acquisition import acquire_native_evidence
    from aptl.core.evidence.adapters.sources import CallableWindowedSource

    request, registration = _trial_request(tmp_path)
    reg_id = registration.registration_id

    def native_sources(_request):
        return {reg_id: CallableWindowedSource(lambda *_: result)}

    selection = dc_replace(
        request.capture_selection,
        contribution=dc_replace(
            request.capture_selection.contribution,
            runtime_adapter=SimpleNamespace(native_sources=native_sources),
        ),
    )
    return acquire_native_evidence(dc_replace(request, capture_selection=selection))


def test_preparation_content_free_failure_records_unknown(tmp_path):
    # A preparation operation that ran and failed may have changed state even
    # when the source supplied no observer-effect string (core-F2). Retain a
    # durable fact with an unknown effect rather than claiming no effect.
    result = _run_native_with_source(
        tmp_path, SourceResult(status=CollectorStatus.MID_RUN_LOSS)
    )
    assert len(result.records) == 1
    refs = _record_source_refs(result.records[0])
    assert ("other", "acquisition-phase:preparation") in refs
    assert ("other", "observer-effect:unknown") in refs


def test_measurement_content_free_failure_without_effect_has_no_record(tmp_path):
    # Measurement observes; a failed observation that reports no effect keeps no
    # evidence reference, preserving the delivery contract (issue #963).
    result = _run_trial_with_source(
        tmp_path, SourceResult(status=CollectorStatus.MID_RUN_LOSS)
    )
    assert result.records == ()


def test_aborting_failure_without_an_operation_keeps_no_record(tmp_path):
    # A source that never started changed nothing, so it leaves no fact record.
    result = _run_native_with_source(
        tmp_path, SourceResult(status=CollectorStatus.SOURCE_UNAVAILABLE)
    )
    assert result.records == ()


def test_retained_failure_outcome_preserves_every_other_field():
    # The retained outcome is built field by field; this fails if a field added
    # to CollectorOutcome is not carried across.
    from dataclasses import fields

    from aptl.core.evidence._persist import retained_failure_outcome
    from aptl.core.evidence.protocol import CollectorOutcome

    original = CollectorOutcome(
        status=CollectorStatus.MID_RUN_LOSS,
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:00:05Z",
        dropped_count=3,
        source_min_time="2026-01-01T00:00:01Z",
        source_max_time="2026-01-01T00:00:04Z",
        observer_effect="probe sent",
        detail="source reported mid-run-loss",
        source_pipeline={"source_refs": []},
    )
    binding = SimpleNamespace(expected_media_types=("application/json",))
    retained = retained_failure_outcome(
        original, binding, AcquisitionPhase.PREPARATION
    )
    overridden = {"chunks", "media_type", "event_count", "observer_effect"}
    for item in fields(CollectorOutcome):
        if item.name not in overridden:
            assert getattr(retained, item.name) == getattr(original, item.name), (
                item.name
            )
    assert retained.media_type == "application/json"
    assert retained.event_count == 1
    assert retained.observer_effect == "probe sent"


def test_nontrial_startup_produces_preparation_labeled_records(tmp_path):
    result = _run_native_with_source(
        tmp_path,
        SourceResult(status=CollectorStatus.OK, records=[{"ready": True}]),
    )
    assert len(result.records) == 1
    refs = _record_source_refs(result.records[0])
    assert ("other", "acquisition-phase:preparation") in refs


def test_failed_capture_evidence_is_durable_on_disk(tmp_path):
    from aptl.backends.raes_evidence_acquisition import acquire_trial_evidence
    from aptl.core.evidence.adapters.sources import CallableWindowedSource

    request, registration = _trial_request(tmp_path)
    result = acquire_trial_evidence(
        request,
        attempt_id="attempt-1",
        sources={
            registration.registration_id: CallableWindowedSource(
                lambda *_: SourceResult(
                    status=CollectorStatus.MID_RUN_LOSS, observer_effect="probe sent"
                )
            )
        },
        trial_body=lambda: None,
    )
    assert len(result.records) == 1
    ledger = (
        request.run_store.get_run_path("run-1")
        / f"evidence/records/{result.records[0].evidence_record_id}.json"
    )
    assert ledger.exists()


def test_on_demand_collector_preserves_observer_effect_on_clock_skew():
    from aptl.backends.raes_evidence_acquisition import _OnDemandNativeCollector
    from aptl.core.evidence.protocol import CollectorContext

    class _Clock:
        def __init__(self, *values):
            self._values = iter(values)

        def now(self):
            return next(self._values)

    class _Source:
        def fetch(self, start, end):
            return SourceResult(
                status=CollectorStatus.OK,
                records=[{"ok": True}],
                observer_effect="probe sent",
                source_max_time="2026-09-14T00:00:30Z",
            )

    context = CollectorContext(
        planned_trial_id="t",
        run_id="run-1",
        attempt_id="provisioning",
        binding=SimpleNamespace(registration_id="r"),
        deadline_seconds=60,
        clock=_Clock("2026-09-14T00:00:00Z", "2026-09-14T00:00:05Z"),
    )
    collector = _OnDemandNativeCollector("r", _Source())
    outcome = collector.stop(collector.start(context))

    assert outcome.status is CollectorStatus.CLOCK_SKEW
    assert outcome.observer_effect == "probe sent"
