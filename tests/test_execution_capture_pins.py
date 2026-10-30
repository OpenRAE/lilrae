"""Run traceability pins the admitted capture spec versions (issue #1372).

RAES evidence satisfaction requires the run's ``(capture spec id, version)``
traceability pins to equal the supplied capture specifications exactly. The
evidence records themselves may omit the version; the run is where it is
pinned (RAES ADR-065). These tests drive real admission into run assembly.
"""

from __future__ import annotations

import dataclasses

import pytest
from raes_contracts.contracts import ExperimentCaptureSpecReferenceModel, ExperimentTaskModel

from aptl.core.correlation.clock import FixedClockProvider
from aptl.core.evidence.content_store import ContentInsertion
from aptl.core.evidence.coordinator import AcquisitionDisposition, AcquisitionResult
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.evidence.protocol import CollectorOutcome, RunScope
from aptl.core.evidence.records import RecordDisclosure, build_evidence_record
from aptl.core.execution.assembly import (
    AdmittedExperiment,
    AssemblyInputs,
    assemble_context,
)
from aptl.core.execution.executor import normalize_terminal_cause
from aptl.core.experiment.admission import AdmissionEnvironment, admit_experiment
from aptl.core.experiment.capture_registry import CollectorRegistry
from aptl.core.experiment.policy import default_admission_policy
from aptl.core.experiment.trial_plan_models import CaptureSpecPin
from aptl.core.runstore import LocalRunStore
from tests.archival_fixtures import reference_run
from tests.test_experiment_admission import (
    _capture_bearing_bundle,
    _covering_registration,
)

_CLOCK = FixedClockProvider("2026-05-26T12:00:00Z")
_LIFECYCLE_PIN = ("aptl.lifecycle", "1.0.0")
_ADMITTED_PIN = ("capture-minimal", "2.3.0")


@pytest.fixture
def admitted(tmp_path) -> AdmittedExperiment:
    """An experiment admitted from an authored capture-spec ref WITHOUT a version.

    Only admission knows the resolved version (2.3.0), so a correct run pin
    can come from nowhere but the admitted pins.
    """
    bundle, backend, processor = _capture_bearing_bundle(
        spec_version="2.3.0", authored_ref_version=None
    )
    result = admit_experiment(
        experiment_root=bundle.experiment_root,
        artifact_source=bundle.artifact_source,
        run_store=LocalRunStore(tmp_path / "plans"),
        policy=default_admission_policy(),
        environment=AdmissionEnvironment(
            backend_manifest=backend, processor_manifest=processor
        ),
        capture_registry=CollectorRegistry((_covering_registration(),)),
    )
    assert result.admitted is True, [d.code for d in result.diagnostics]
    run = reference_run()
    return AdmittedExperiment(
        plan=result.plan,
        task=ExperimentTaskModel.model_validate_json(bundle.task_bytes),
        scenario_snapshot_ref=run.scenario_snapshot_ref,
        apparatus_context=run.apparatus_context,
        capture_spec_pins=result.capture_spec_pins,
    )


def _attempt_id(admitted: AdmittedExperiment) -> str:
    return f"{admitted.plan.trials[0].planned_trial_id}-attempt-1"


def _record(admitted: AdmittedExperiment, digest_hex: str):
    """A real coordinator-built record for the admitted binding (version omitted)."""
    return build_evidence_record(
        binding=admitted.plan.capture_bindings[0],
        run_id=_attempt_id(admitted),
        planned_trial_id=admitted.plan.trials[0].planned_trial_id,
        content=ContentInsertion(
            relative_path=f"evidence/{digest_hex}",
            digest=f"sha256:{digest_hex}",
            size=3,
            truncated=False,
        ),
        outcome=CollectorOutcome(
            status=CollectorStatus.OK,
            started_at="2026-05-26T12:00:00Z",
            finished_at="2026-05-26T12:00:01Z",
            event_count=1,
        ),
        captured_at="2026-05-26T12:00:01Z",
        disclosure=RecordDisclosure(sensitivity="internal", redaction_state="none"),
    )


def _with_spec_ref(record, *, ref_id: str, ref_version: str | None):
    return record.model_copy(
        update={
            "capture_spec_ref": ExperimentCaptureSpecReferenceModel(
                ref_kind="capture-spec", ref_id=ref_id, ref_version=ref_version
            )
        }
    )


def _assemble(store: LocalRunStore, admitted: AdmittedExperiment, records=()):
    attempt_id = _attempt_id(admitted)
    store.create_run(attempt_id)
    disposition = (
        AcquisitionDisposition.SEALED_READY
        if records
        else AcquisitionDisposition.INCONCLUSIVE
    )
    return assemble_context(
        store,
        _CLOCK,
        AssemblyInputs(
            admitted=admitted,
            planned_trial=admitted.plan.trials[0],
            attempt_id=attempt_id,
            scope=RunScope(
                run_id=attempt_id,
                planned_trial_id=admitted.plan.trials[0].planned_trial_id,
                attempt_id=attempt_id,
            ),
            acquisition=AcquisitionResult(
                disposition=disposition,
                records=tuple(records),
                refs=(),
                reports=(),
                diagnostics=(),
            ),
            outcome=None,
            resolution=normalize_terminal_cause(None, disposition),
            started_at=_CLOCK.now(),
            ended_at=_CLOCK.now(),
        ),
    )


def _pins(context) -> list[tuple[str, str | None]]:
    return [
        (ref.ref_id, ref.ref_version)
        for ref in context.traceability.capture_spec_refs
    ]


class TestAdmittedVersionsReachTheRun:
    def test_run_pins_equal_the_admitted_capture_specs(self, tmp_path, admitted):
        # Two records share one capture spec and both omit its version.
        records = [_record(admitted, "aa" * 32), _record(admitted, "bb" * 32)]
        assert all(r.capture_spec_ref.ref_version is None for r in records)

        context = _assemble(LocalRunStore(tmp_path / "runs"), admitted, records)

        assert _pins(context) == [_LIFECYCLE_PIN, _ADMITTED_PIN]
        assert {ref.ref_id for ref in context.traceability.evidence_record_refs} >= {
            r.evidence_record_id for r in records
        }

    def test_a_capture_without_records_still_pins_the_admitted_spec(
        self, tmp_path, admitted
    ):
        context = _assemble(LocalRunStore(tmp_path / "runs"), admitted)

        assert _pins(context) == [_LIFECYCLE_PIN, _ADMITTED_PIN]
        assert len(context.traceability.evidence_record_refs) == 1  # lifecycle only

    def test_a_record_carrying_the_admitted_version_is_accepted(
        self, tmp_path, admitted
    ):
        record = _with_spec_ref(
            _record(admitted, "aa" * 32), ref_id="capture-minimal", ref_version="2.3.0"
        )

        context = _assemble(LocalRunStore(tmp_path / "runs"), admitted, [record])

        assert _pins(context) == [_LIFECYCLE_PIN, _ADMITTED_PIN]


class TestRecordsMustAgreeWithThePins:
    @pytest.mark.parametrize(
        ("ref_id", "ref_version", "match"),
        [
            ("capture-minimal", "1.0.0", "admission resolved '2.3.0'"),
            ("capture-unadmitted", None, "not an admitted capture spec"),
        ],
    )
    def test_a_disagreeing_record_fails_before_any_write(
        self, tmp_path, admitted, ref_id, ref_version, match
    ):
        store = LocalRunStore(tmp_path / "runs")
        record = _with_spec_ref(
            _record(admitted, "aa" * 32), ref_id=ref_id, ref_version=ref_version
        )

        with pytest.raises(ValueError, match=match):
            _assemble(store, admitted, [record])

        run_dir = tmp_path / "runs" / _attempt_id(admitted)
        assert list(run_dir.iterdir()) == []


class TestTheHandoffPinsExactlyThePlannedSpecs:
    @pytest.mark.parametrize(
        ("pins", "match"),
        [
            ((), "unpinned \\['capture-minimal'\\]"),
            (
                (_ADMITTED_PIN, ("capture-extra", "1.0.0")),
                "unreferenced \\['capture-extra'\\]",
            ),
            ((_ADMITTED_PIN, ("capture-minimal", "9.9.9")), "each capture spec once"),
            ((_ADMITTED_PIN, _LIFECYCLE_PIN), "reserved for the executor lifecycle"),
            ((("capture-minimal", None),), "non-empty capture spec id and version"),
            ((("capture-minimal", ""),), "non-empty capture spec id and version"),
        ],
    )
    def test_a_mismatched_pin_set_is_rejected(self, admitted, pins, match):
        with pytest.raises(ValueError, match=match):
            dataclasses.replace(admitted, capture_spec_pins=pins)

    def test_the_pins_are_an_immutable_snapshot(self, admitted):
        caller_pins = [list(_ADMITTED_PIN)]

        snapshot = dataclasses.replace(admitted, capture_spec_pins=caller_pins)
        caller_pins[0][1] = "6.6.6"

        assert snapshot.capture_spec_pins == (CaptureSpecPin(*_ADMITTED_PIN),)
