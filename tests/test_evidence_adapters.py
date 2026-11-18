"""Tests for the evidence collector adapters (EXP-010 / issue #752 PR 2).

Covers the generic windowed-query collector, the concrete built-in sources
(each distinguishing a source failure from legitimate emptiness at the owner
level — never the empty-on-error collapse), and the trusted wiring seam.
"""

from __future__ import annotations

import json
import types


from aptl.core.correlation.clock import FixedClockProvider
from aptl.core.deployment._compose_log_capture import StreamExit
from aptl.core.evidence.adapters.builtins import (
    ContainerLogSource,
    RunArchiveSource,
    soc_windowed_source,
)
from aptl.core.evidence.adapters.sources import SourceResult, WindowedQueryCollector
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.evidence.protocol import CollectorContext
from aptl.core.experiment.capture_registry import (
    CaptureBinding,
    CaptureVisibility,
)
from aptl.core.runstore import LocalRunStore

_CLOCK = FixedClockProvider(measurement_time="2026-07-20T00:00:00Z")


def _binding(registration_id="aptl.collector.mcp-red") -> CaptureBinding:
    return CaptureBinding(
        capture_spec_id="cap-1",
        requirement_id="req-a",
        window_refs=("run-window",),
        registration_id=registration_id,
        implementation_version="1.0.0",
        contract_version="experiment-capture-spec/v1",
        effective_config_digest="sha256:" + "cd" * 32,
        channel_ref_id="chan",
        channel_ref_version="1.0.0",
        channel_kind="participant-observation",
        capture_kind="observation",
        capture_scope="participant",
        expected_media_types=("application/json",),
        required_artifact_roles=("observation",),
        sensitivity="internal",
        redaction_required=False,
        integrity_requirements=("sha256-digest",),
        retention_policy="retain",
        loss_disclosure_required=True,
        visibility_class=CaptureVisibility.PARTICIPANT_VISIBLE,
    )


def _context(registration_id="aptl.collector.mcp-red") -> CollectorContext:
    return CollectorContext(
        planned_trial_id="trial-1",
        run_id="run-1",
        attempt_id="attempt-1",
        binding=_binding(registration_id),
        progress_timeout_seconds=60.0,
        clock=_CLOCK,
    )


class _FakeSource:
    def __init__(self, result: SourceResult) -> None:
        self._result = result

    def fetch(self, start_iso, end_iso) -> SourceResult:
        return self._result


class TestWindowedQueryCollector:
    def test_records_map_to_ok_with_json_bytes(self):
        source = _FakeSource(
            SourceResult(status=CollectorStatus.OK, records=[{"a": 1}, {"a": 2}])
        )
        collector = WindowedQueryCollector("aptl.collector.mcp-red", source)
        outcome = collector.stop(collector.start(_context()))
        assert outcome.status is CollectorStatus.OK
        assert outcome.event_count == 2
        assert outcome.media_type == "application/json"
        assert b'"a":1' in b"".join(outcome.chunks)

    def test_empty_records_are_empty_ok(self):
        source = _FakeSource(SourceResult(status=CollectorStatus.EMPTY_OK, records=[]))
        collector = WindowedQueryCollector("aptl.collector.mcp-red", source)
        outcome = collector.stop(collector.start(_context()))
        assert outcome.status is CollectorStatus.EMPTY_OK

    def test_source_failure_passes_through_without_chunks(self):
        source = _FakeSource(SourceResult(status=CollectorStatus.SOURCE_UNAVAILABLE))
        collector = WindowedQueryCollector("aptl.collector.mcp-red", source)
        outcome = collector.stop(collector.start(_context()))
        assert outcome.status is CollectorStatus.SOURCE_UNAVAILABLE
        assert not outcome.chunks


class TestRunArchiveSource:
    def test_missing_subtree_is_source_unavailable(self, tmp_path):
        store = LocalRunStore(tmp_path / "runs")
        store.create_run("run-1")
        source = RunArchiveSource(store, "run-1", "mcp-side")
        assert source.fetch("s", "e").status is CollectorStatus.SOURCE_UNAVAILABLE

    def test_present_but_empty_is_empty_ok(self, tmp_path):
        store = LocalRunStore(tmp_path / "runs")
        store.write_file("run-1", "mcp-side/tool-calls.jsonl", b"")
        source = RunArchiveSource(store, "run-1", "mcp-side")
        assert source.fetch("s", "e").status is CollectorStatus.EMPTY_OK

    def test_records_are_read_and_malformed_lines_dropped(self, tmp_path):
        store = LocalRunStore(tmp_path / "runs")
        store.write_file(
            "run-1", "mcp-side/tool-calls.jsonl", b'{"a": 1}\nnot-json\n{"a": 2}\n'
        )
        source = RunArchiveSource(store, "run-1", "mcp-side")
        result = source.fetch("s", "e")
        assert result.status is CollectorStatus.OK
        assert len(result.records) == 2
        assert result.dropped_count == 1


def _log_backend(
    returncode: int, stdout: bytes = b"", stderr: bytes = b"", **flags: bool
) -> types.SimpleNamespace:
    """Return a backend whose log stream writes fixed output into the spools."""

    def stream(name, *, since, until, stdout: object, stderr: object) -> StreamExit:
        stdout.write(out)
        stderr.write(err)
        return StreamExit(
            returncode, flags.get("timed_out", False), flags.get("failed_pipe", False)
        )

    out, err = stdout, stderr
    return types.SimpleNamespace(container_logs_stream=stream)


def _records(result: SourceResult) -> list[dict[str, object]]:
    return json.loads(b"".join(result.chunks))


class TestContainerLogSource:
    def test_nonzero_returncode_is_source_unavailable(self):
        source = ContainerLogSource(_log_backend(1), ["c1"])
        assert source.fetch("s", "e").status is CollectorStatus.SOURCE_UNAVAILABLE

    def test_empty_output_is_empty_ok(self):
        source = ContainerLogSource(_log_backend(0), ["c1"])
        assert source.fetch("s", "e").status is CollectorStatus.EMPTY_OK

    def test_output_becomes_records(self):
        source = ContainerLogSource(_log_backend(0, b"line1\nline2"), ["c1"])
        result = source.fetch("s", "e")
        assert result.status is CollectorStatus.OK
        assert _records(result) == [{"container": "c1", "output": "line1\nline2"}]

    def test_large_output_is_retained_completely(self):
        output = b"event\n" * 400_000
        source = ContainerLogSource(_log_backend(0, output, b"warn"), ["c1"])
        result = source.fetch("s", "e")
        assert result.status is CollectorStatus.OK
        record = _records(result)[0]
        assert record["output"] == output.decode()
        assert record["stderr"] == "warn"

    def test_stalled_read_keeps_accepted_output_as_timeout(self):
        source = ContainerLogSource(
            _log_backend(None, b"accepted\n", timed_out=True), ["c1"]
        )
        result = source.fetch("s", "e")
        assert result.status is CollectorStatus.TIMEOUT
        assert _records(result) == [
            {"container": "c1", "status": "timeout", "output": "accepted\n"}
        ]


class TestSocWindowedSource:
    def test_none_is_source_unavailable(self):
        source = soc_windowed_source(lambda s, e: None)
        assert source.fetch("s", "e").status is CollectorStatus.SOURCE_UNAVAILABLE

    def test_empty_list_is_empty_ok(self):
        source = soc_windowed_source(lambda s, e: [])
        assert source.fetch("s", "e").status is CollectorStatus.EMPTY_OK

    def test_events_are_ok(self):
        source = soc_windowed_source(lambda s, e: [{"alert": 1}])
        result = source.fetch("s", "e")
        assert result.status is CollectorStatus.OK
        assert result.records == [{"alert": 1}]
