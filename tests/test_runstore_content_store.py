"""Tests for the content-addressed + run-scoped create-once evidence
persistence functions (EXP-010 / issue #752 evidence acquisition).

``create_content_addressed`` streams raw evidence into a digest-named object
under the run dir without a byte cap, no-follow / create-exclusive
publication, a free-space reserve, and post-write digest verification.
``create_run_json_once`` is the run-scoped create-once JSON writer (travels in
the exporter's per-run tar). Both extend the ``LocalRunStore`` boundary
narrowly rather than adding a second repository.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from aptl.core.evidence.content_store import create_content_addressed, create_run_json_once
from aptl.core.runstore import LocalRunStore, RunStoreConflictError
from aptl.utils.pathsafe_stream import FreeSpaceReserveError


def _store(tmp_path) -> LocalRunStore:
    """Return a LocalRunStore rooted at a fresh temp dir."""
    return LocalRunStore(tmp_path / "runs")


# ---------------------------------------------------------------------------
# create_content_addressed
# ---------------------------------------------------------------------------


class TestContentAddressed:
    def test_stores_under_digest_named_path_and_returns_metadata(self, tmp_path):
        store = _store(tmp_path)
        payload = b"raw evidence bytes"
        digest_hex = hashlib.sha256(payload).hexdigest()

        result = create_content_addressed(store, "run-1", [payload], subdir="evidence")

        assert result.relative_path == f"evidence/{digest_hex}"
        assert result.digest == f"sha256:{digest_hex}"
        assert result.size == len(payload)
        stored = (store.get_run_path("run-1") / result.relative_path).read_bytes()
        assert stored == payload

    def test_streams_multiple_chunks(self, tmp_path):
        store = _store(tmp_path)
        chunks = [b"aaa", b"bbb", b"ccc"]
        joined = b"".join(chunks)

        result = create_content_addressed(store, "run-1", chunks, subdir="evidence")

        assert result.size == len(joined)
        assert result.digest == f"sha256:{hashlib.sha256(joined).hexdigest()}"

    def test_large_streamed_source_is_retained_completely(self, tmp_path):
        store = _store(tmp_path)
        chunks = [bytes([index]) * 1_048_576 for index in range(9)]
        joined = b"".join(chunks)

        result = create_content_addressed(store, "run-1", iter(chunks), subdir="evidence")

        assert result.size == len(joined)
        stored = (store.get_run_path("run-1") / result.relative_path).read_bytes()
        assert stored == joined

    def test_free_space_reserve_fails_and_leaves_no_file(self, tmp_path):
        store = LocalRunStore(tmp_path / "runs", free_space_reserve=0.999999)
        store.create_run("run-1")

        with pytest.raises(FreeSpaceReserveError):
            create_content_addressed(store, "run-1", [b"x"], subdir="evidence")

        directory = store.get_run_path("run-1") / "evidence"
        assert not directory.exists() or list(directory.iterdir()) == []

    def test_identical_bytes_are_idempotent(self, tmp_path):
        store = _store(tmp_path)
        first = create_content_addressed(store, "run-1", [b"same"], subdir="evidence")
        second = create_content_addressed(store, "run-1", [b"same"], subdir="evidence")
        assert first == second
        directory = store.get_run_path("run-1") / "evidence"
        assert [path.name for path in directory.iterdir()] == [first.digest[7:]]

    def test_traversal_subdir_is_rejected(self, tmp_path):
        store = _store(tmp_path)
        with pytest.raises(ValueError):
            create_content_addressed(store, "run-1", [b"x"], subdir="../escape")


# ---------------------------------------------------------------------------
# create_run_json_once
# ---------------------------------------------------------------------------


class TestRunJsonOnce:
    def test_preserves_scenario_credentials_and_assertion_results(self, tmp_path):
        store = _store(tmp_path)
        payload = {"proposition_truth_results": {"evaluation.assertion.demo-credentials-present": {"assertion_outcome": "false", "password": "scenario-fixture"}}}
        target = create_run_json_once(store, "run-1", "trial/evaluation.json", payload)
        assert json.loads(target.read_bytes()) == payload

    def test_writes_under_the_run_dir(self, tmp_path):
        store = _store(tmp_path)
        target = create_run_json_once(store, "run-1", "evidence/records/rec-1.json", {"a": 1})
        assert target.is_relative_to(store.get_run_path("run-1"))
        assert target.exists()

    def test_identical_payload_is_idempotent(self, tmp_path):
        store = _store(tmp_path)
        first = create_run_json_once(store, "run-1", "evidence/r.json", {"a": 1, "b": 2})
        second = create_run_json_once(store, "run-1", "evidence/r.json", {"b": 2, "a": 1})
        assert first == second

    def test_different_payload_conflicts(self, tmp_path):
        store = _store(tmp_path)
        create_run_json_once(store, "run-1", "evidence/r.json", {"a": 1})
        with pytest.raises(RunStoreConflictError):
            create_run_json_once(store, "run-1", "evidence/r.json", {"a": 2})
