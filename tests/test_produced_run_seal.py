"""Seal producer-owned records without changing their portable semantics."""

import pytest
from raes_contracts.contracts import ExperimentRunModel

from aptl.core.archival.discovery_index import DiscoveryIndex
from aptl.core.archival.verify import SealVerificationError, verify_sealed_archive
from aptl.core.runstore import LocalRunStore
from tests.archival_fixtures import reference_run


def partial_run():
    payload = reference_run().model_dump(mode="json")
    payload.update(
        record_state="partial",
        run_status="indeterminate",
        outcome_status="not-evaluated",
        ended_at=None,
        run_version="partial-" + "a" * 64,
        execution_accounting={
            "plan_id": "plan-a",
            "plan_digest": "sha256:" + "a" * 64,
            "plan_entry_id": "entry-a",
            "entry_digest": "sha256:" + "b" * 64,
            "attempts": [
                {
                    "execution_attempt_id": "attempt-a",
                    "attempt": 1,
                    "started_at": payload["started_at"],
                    "execution_status": "unknown",
                }
            ],
        },
    )
    return ExperimentRunModel.model_validate(payload)


def test_seal_preserves_produced_partial_record_and_long_version(tmp_path):
    run = partial_run()
    from aptl.core.archival.coordinator import seal_produced_run

    store = LocalRunStore(tmp_path / "archives")
    result = seal_produced_run(
        run, store=store, observed_at="2026-11-03T22:00:00Z"
    )
    assert result.run == run
    assert store.get_run_manifest(run.run_id) == run.model_dump(mode="json")
    verified = verify_sealed_archive(store.base_dir, run.run_id)
    assert verified.run_id == run.run_id
    assert verified.run_version == run.run_version
    assert result.run.ended_at is None
    assert store.read_seal_marker(run.run_id)["completeness"]["complete"] is False
    assert DiscoveryIndex(store.base_dir).discover()[0].run_version == run.run_version


def test_duplicate_seal_verifies_manifest_integrity(tmp_path):
    run = reference_run()
    from aptl.core.archival.coordinator import seal_produced_run

    store = LocalRunStore(tmp_path / "archives")
    first = seal_produced_run(run, store=store)
    duplicate = seal_produced_run(run, store=store)
    assert duplicate.idempotent
    assert duplicate.run_record_digest == first.run_record_digest
    first.manifest_path.write_bytes(b"{}")
    with pytest.raises(SealVerificationError):
        seal_produced_run(run, store=store)


def test_duplicate_seal_finishes_index_commit_after_interruption(tmp_path):
    run = reference_run()
    from aptl.core.archival.coordinator import seal_produced_run

    store = LocalRunStore(tmp_path / "archives")

    class InterruptedIndex(DiscoveryIndex):
        def commit(self, entry):
            raise OSError("interrupted after seal")

    with pytest.raises(OSError, match="interrupted after seal"):
        seal_produced_run(run, store=store, index=InterruptedIndex(store.base_dir))
    assert verify_sealed_archive(store.base_dir, run.run_id) is not None
    duplicate = seal_produced_run(run, store=store)
    assert duplicate.idempotent
    assert DiscoveryIndex(store.base_dir).discover()[0].run_id == run.run_id
