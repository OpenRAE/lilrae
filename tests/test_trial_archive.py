"""Immutable recovery snapshots preserve original partial bytes and facts."""

import pytest

from aptl.core.archival.verify import verify_sealed_archive
from aptl.core.correlation.clock import FixedClockProvider
from raes_runtime.errors import TrialPending
from tests.trial_recovery_fixture import assigned_serving


def seal_case(case, *, clock=None):
    from aptl.backends.trial_archive import seal_recovered_run

    bundle = case.records()
    return seal_recovered_run(
        bundle.runs[0],
        source=bundle.sources[0],
        outcome=case.binding.outcome(identity="worker-437"),
        assignment=case.binding.assignment,
        store=case.handler.cleanup.store,
        clock=clock or case.clock,
        validation_passed=bundle.validation_by_run[bundle.runs[0].run_id] == "passed",
    )


def test_recovery_archive_retains_partial_bytes_without_sealing_working_store(tmp_path):
    with assigned_serving(tmp_path) as case:
        store, run_id = case.handler.cleanup.store, case.binding.request.run_id
        store.write_file(run_id, "evidence/raw/capture.partial", b"retained tail\n")
        first = seal_case(case)
        assert first.run.run_id == run_id
        assert first.run.run_status == "indeterminate"
        assert first.run.ended_at is None
        assert first.manifest_path.parent.joinpath("evidence/raw/capture.partial").read_bytes() == b"retained tail\n"
        assert not store.is_sealed(run_id)
        assert verify_sealed_archive(first.manifest_path.parent.parent, run_id) is not None
        before = first.seal_marker_path.read_bytes()
        duplicate = seal_case(
            case, clock=FixedClockProvider(measurement_time="2026-11-03T22:01:00Z")
        )
        assert duplicate.manifest_path == first.manifest_path
        assert duplicate.idempotent
        assert duplicate.seal_marker_path.read_bytes() == before
        store.write_json(run_id, "cleanup/later.json", {"state": "unverified"})
        later = seal_case(case)
        assert later.manifest_path != first.manifest_path
        assert later.run.run_id == first.run.run_id
        assert first.seal_marker_path.read_bytes() == before


def test_archive_refuses_symlinked_source_without_exposing_its_content(tmp_path):
    with assigned_serving(tmp_path) as case:
        store, run_id = case.handler.cleanup.store, case.binding.request.run_id
        outside = tmp_path / "outside-canary"
        outside.write_bytes(b"private-canary-437")
        (store.get_run_path(run_id) / "escape").symlink_to(outside)
        with pytest.raises(ValueError, match="trial-archive-") as failure:
            seal_case(case)
        assert "private-canary-437" not in str(failure.value)
        assert outside.read_bytes() == b"private-canary-437"


def test_archive_refuses_bytes_that_disagree_with_original_evidence(tmp_path):
    with assigned_serving(tmp_path) as case:
        with pytest.raises(TrialPending):
            case.handler.execute_trial(case.binding.request)
        outcome = case.binding.outcome(identity="worker-437")
        case.coordinator.ingest_trial_outcome(case.experiment_id, outcome)
        original = seal_case(case)
        assert original.seal_marker_path.is_file()
        record = next(iter(case.services.records.values()))
        path = case.handler.cleanup.store.get_run_path(record.run_ref.ref_id) / record.raw_content.content_uri
        path.write_bytes(b"substituted capture")
        with pytest.raises(ValueError, match="trial-archive-"):
            seal_case(case)
