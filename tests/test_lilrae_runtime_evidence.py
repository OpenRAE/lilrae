"""The supported collector handoff preserves owner-produced proof bytes."""

from dataclasses import replace
from io import BytesIO
import hashlib
import json
import zipfile

import pytest

from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.experiment.capture_registry import CaptureLimits, CaptureVisibility
from aptl.core.runstore import LocalRunStore
from tests.test_evidence_adapters import _binding
from tests.test_lilrae_runtime_inventory_reporting import reporting_runtime


def _protected_binding():
    return replace(
        _binding("lilrae.collector.native-evidence"),
        expected_media_types=("application/zip",),
        sensitivity="restricted",
        visibility_class=CaptureVisibility.APPARATUS_ONLY,
        limits=CaptureLimits(4 * 1024 * 1024, 128, 60),
    )


def _started(tmp_path, monkeypatch):
    from aptl.backends.raes import _run_execution_plan

    previous, _, native, child, plan, _ = reporting_runtime(tmp_path)
    target = previous._target
    previous.close()
    original = b'{"schema":1,"attempt_id":"run-1","native_id":"proof"}\n  '
    artifacts = [("native-resource-receipt/v1", original)]
    native.native_evidence_artifacts = lambda attempt: tuple(artifacts)
    monkeypatch.setattr(
        "aptl.backends.raes.interpret_realization", lambda *args: ({}, [], {})
    )
    store = LocalRunStore(tmp_path / "protected-runs")
    outcome = _run_execution_plan(target, plan, run_store=store, run_id="run-1")
    assert outcome.lab_result.success, outcome.lab_result.error
    return outcome, plan, store, artifacts, child


def _unpack(source):
    result = source.fetch("start", "end")
    assert result.status is CollectorStatus.OK
    assert result.media_type == "application/zip"
    archive = zipfile.ZipFile(BytesIO(b"".join(result.chunks)))
    return json.loads(archive.read("index.json")), archive


def test_public_outcome_retains_original_sdl_snapshot_and_native_bytes(
    tmp_path, monkeypatch
):
    outcome, plan, _, artifacts, child = _started(tmp_path, monkeypatch)
    manager = outcome.runtime_manager
    try:
        handoff = outcome.native_evidence
        assert handoff is manager.native_evidence
        receipt = manager.evaluate(plan, idempotency_key="new-evidence-cut")
        assert receipt.accepted
        index, archive = _unpack(handoff.source(_protected_binding()))
        with archive:
            assert index["run_id"] == index["attempt_id"] == "run-1"
            assert {cut["phase"] for cut in index["cuts"]} >= {
                "initial",
                "inventory",
                "evaluation",
            }
            for cut in index["cuts"]:
                assert cut["plan_digest"].startswith("sha256:")
                assert set(cut["producer_versions"]) == {"lilrae", "raes", "raes-env-packs"}
                assert cut["recorded_at"]
                if cut["phase"] == "evaluation":
                    assert cut["operation"]["operation_id"] == receipt.operation_id
                    assert cut["success"] is None
                for artifact in cut["artifacts"]:
                    data = archive.read(artifact["path"])
                    assert hashlib.sha256(data).hexdigest() == artifact["sha256"]
                    assert len(data) == artifact["size_bytes"]
                    if artifact["role"] == "runtime-snapshot":
                        snapshot = json.loads(data)
                        assert child.address in snapshot["entries"]
                        assert any(
                            row["address"] == child.address
                            for row in snapshot["realization_provenance"]
                        )
                    if artifact["role"] == "materialized-sdl":
                        record = artifact["archive_record"]
                        assert len(data) == record["artifact"]["size_bytes"]
                        assert (
                            hashlib.sha256(data).hexdigest()
                            == record["artifact"]["checksum"]["value"]
                        )
            assert any(
                archive.read(item["path"]) == artifacts[0][1]
                for item in index["native_artifacts"]
            )
    finally:
        manager.close()


@pytest.mark.parametrize(
    "change",
    [
        {"visibility_class": CaptureVisibility.PARTICIPANT_VISIBLE},
        {"redaction_required": True},
        {"sensitivity": "public"},
    ],
)
def test_protected_handoff_refuses_disclosure_or_byte_rewriting(
    tmp_path, monkeypatch, change
):
    outcome, _, _, _, _ = _started(tmp_path, monkeypatch)
    try:
        with pytest.raises(ValueError, match="protected"):
            outcome.native_evidence.source(replace(_protected_binding(), **change))
    finally:
        outcome.runtime_manager.close()


def test_handoff_reads_final_native_cleanup_without_mutating_a_sealed_run(
    tmp_path, monkeypatch
):
    outcome, _, store, artifacts, _ = _started(tmp_path, monkeypatch)
    outcome.runtime_manager.close()
    monkeypatch.setattr(store, "is_sealed", lambda _run_id: True)
    before = {
        p.relative_to(store.base_dir): p.read_bytes()
        for p in store.base_dir.rglob("*")
        if p.is_file()
    }
    cleanup = (
        b'{"schema":"lilrae.native-cleanup/v1","attempt_id":"run-1","state":"absent"}\n'
    )
    artifacts.append(("native-cleanup/v1", cleanup))
    index, archive = _unpack(outcome.native_evidence.source(_protected_binding()))
    with archive:
        assert any(
            archive.read(item["path"]) == cleanup for item in index["native_artifacts"]
        )
    assert before == {
        p.relative_to(store.base_dir): p.read_bytes()
        for p in store.base_dir.rglob("*")
        if p.is_file()
    }


def test_changed_proof_and_over_limit_handoff_never_become_empty_success(
    tmp_path, monkeypatch
):
    outcome, _, store, _, _ = _started(tmp_path, monkeypatch)
    outcome.runtime_manager.close()
    binding = _protected_binding()
    source = outcome.native_evidence.source(
        replace(binding, limits=CaptureLimits(1, 1, 60))
    )
    assert source.fetch("start", "end").status is CollectorStatus.TRUNCATION
    index, archive = _unpack(outcome.native_evidence.source(binding))
    with archive:
        artifact = index["cuts"][0]["artifacts"][0]
    (store.get_run_path("run-1") / "native-evidence" / artifact["path"]).write_bytes(
        b"changed"
    )
    result = outcome.native_evidence.source(binding).fetch("start", "end")
    assert result.status is CollectorStatus.SOURCE_UNAVAILABLE
    assert not result.chunks
