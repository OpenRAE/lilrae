"""Captured evidence is retained complete, without byte caps or truncation."""

from __future__ import annotations

import hashlib
import json

from aptl.core.correlation.clock import FixedClockProvider
from aptl.core.evidence._persist import persist_success_outcome
from aptl.core.evidence.coordinator import acquire_evidence
from aptl.core.evidence.outcomes import AcquisitionDisposition, CollectorStatus
from aptl.core.evidence.protocol import CollectorOutcome, RunScope
from aptl.core.runstore import LocalRunStore
from tests.test_evidence_records import _binding

_MIB = 1024 * 1024


def _large_jsonl() -> list[bytes]:
    """Return nine 1 MiB JSON-lines chunks, larger than any former capture cap."""
    line = json.dumps({"event": "x" * 1000}).encode() + b"\n"
    per_chunk = _MIB // len(line)
    return [line * per_chunk for _ in range(9)]


def _outcome(chunks, media_type="application/x-ndjson") -> CollectorOutcome:
    return CollectorOutcome(
        status=CollectorStatus.OK,
        started_at="2026-07-20T00:00:00Z",
        finished_at="2026-07-20T00:00:05Z",
        chunks=chunks,
        media_type=media_type,
        event_count=len(chunks),
    )


def test_a_large_multi_chunk_capture_is_stored_complete(tmp_path):
    chunks = _large_jsonl()
    data = b"".join(chunks)
    store = LocalRunStore(tmp_path)
    store.create_run("run-1")

    retained = persist_success_outcome(
        binding=_binding(expected_media_types=("application/x-ndjson",)),
        outcome=_outcome(iter(chunks)),
        run_store=store,
        run_id="run-1",
        planned_trial_id="trial-1",
    )

    stored = (tmp_path / "run-1" / retained.ref.content_uri).read_bytes()
    assert len(data) > 8 * _MIB
    assert stored == data
    assert retained.ref.content_digest == f"sha256:{hashlib.sha256(data).hexdigest()}"
    assert retained.effective_status is CollectorStatus.OK
    assert retained.record.raw_content.loss_disclosure is None


def test_a_binding_with_a_policy_records_the_redacted_state(tmp_path):
    store = LocalRunStore(tmp_path)
    store.create_run("run-1")

    retained = persist_success_outcome(
        binding=_binding(redaction_required=True, redaction_policy="redact_secrets"),
        outcome=_outcome([b'[{"password":"hunter2","ok":1}]'], "application/json"),
        run_store=store,
        run_id="run-1",
        planned_trial_id="trial-1",
    )

    stored = (tmp_path / "run-1" / retained.ref.content_uri).read_text()
    assert retained.record.redaction_state == "redacted"
    assert retained.record.redaction_policy == "redact_secrets"
    assert "hunter2" not in stored
    assert json.loads(stored)[0]["ok"] == 1


class _Collector:
    registration_id = "aptl.collector.a"

    def __init__(self, outcome):
        self._outcome = outcome

    def start(self, context):
        return context

    def stop(self, handle):
        return self._outcome


def test_a_reached_free_space_reserve_fails_the_capture_visibly(tmp_path):
    store = LocalRunStore(tmp_path / "runs", free_space_reserve=0.999999)
    store.create_run("run-1")
    binding = _binding(registration_id="aptl.collector.a")

    result = acquire_evidence(
        bindings=[binding],
        collectors={"aptl.collector.a": _Collector(_outcome([b'{"a":1}\n']))},
        run_store=store,
        scope=RunScope("run-1", "trial-1", "attempt-1"),
        clock=FixedClockProvider(measurement_time="2026-07-20T00:00:00Z"),
    )

    assert [report.status for report in result.reports] == [
        CollectorStatus.FINALIZATION_FAILURE
    ]
    assert result.disposition is AcquisitionDisposition.INVALIDATED
    assert not list((tmp_path / "runs" / "run-1").rglob("evidence/blobs/*"))


def test_the_store_progress_timeout_reaches_collectors(tmp_path):
    store = LocalRunStore(tmp_path / "runs", progress_timeout_seconds=7.5)
    store.create_run("run-1")
    seen = []

    class Recording(_Collector):
        def start(self, context):
            seen.append(context.progress_timeout_seconds)
            return context

    acquire_evidence(
        bindings=[_binding(registration_id="aptl.collector.a")],
        collectors={"aptl.collector.a": Recording(_outcome([b'{"a":1}\n']))},
        run_store=store,
        scope=RunScope("run-1", "trial-1", "attempt-1"),
        clock=FixedClockProvider(measurement_time="2026-07-20T00:00:00Z"),
    )

    assert seen == [7.5]
