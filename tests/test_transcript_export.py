"""The teardown transcript export names the step that left it without a payload."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from aptl.backends._raes_transcript_export import (
    TRANSCRIPT_EXPORT_FAILED,
    TranscriptExportFailure,
    export_transcript_payload,
    unaccepted_attempt_ref,
)
from aptl.core.deployment.errors import CaptureReconciliationError

_BINDING = SimpleNamespace(limits=SimpleNamespace(max_artifact_count=8))


def _census(tmp_path, *names):
    """Write an MCP session census for run-1 and return the run store base."""
    census = tmp_path / "run-1/mcp-side/sessions"
    census.mkdir(parents=True)
    for name in names:
        (census / name).write_text("")
    return tmp_path


def _backend(*, quiesced=True, export=None):
    """Return a capture apparatus whose export calls are recorded."""
    calls = []

    def export_capture_apparatus(*, expected_session_ids):
        calls.append(expected_session_ids)
        return export(expected_session_ids) if callable(export) else export

    backend = SimpleNamespace(
        quiesce_capture_apparatus=lambda: quiesced,
        export_capture_apparatus=export_capture_apparatus,
    )
    return backend, calls


def test_a_matching_export_records_no_failed_attempts(tmp_path):
    """A census the broker fully accepted keeps every session."""
    payload = {"accepted_session_ids": ["session-1"]}
    backend, calls = _backend(export=payload)

    exported, failure = export_transcript_payload(
        backend, _census(tmp_path, "session-1.jsonl"), "run-1", _BINDING
    )

    assert failure is None
    assert exported == {
        **payload,
        "expected_session_ids": ["session-1"],
        "unaccepted_attempts": {"count": 0, "refs": []},
    }
    assert calls == [("session-1",)]


def _tee(store_base, session_id, *records):
    """Write one census tee for run-1 as JSONL records."""
    path = store_base / "run-1/mcp-side/sessions" / f"{session_id}.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in records))


@pytest.mark.parametrize(
    "records",
    [(), ({"ts": 1, "dir": "err", "b64": "VHJhY2ViYWNr"},)],
    ids=("empty-tee", "error-only-tee"),
)
def test_a_census_session_that_never_opened_is_a_failed_attempt(tmp_path, records):
    """A refused or unopened session is excluded and recorded by hashed ref."""
    store_base = _census(tmp_path, "ops.jsonl", "session-1.jsonl")
    _tee(store_base, "ops", *records)
    backend, _calls = _backend(export={"accepted_session_ids": ["session-1"]})

    exported, failure = export_transcript_payload(
        backend, store_base, "run-1", _BINDING
    )

    assert failure is None
    assert exported["expected_session_ids"] == ["session-1"]
    assert exported["unaccepted_attempts"] == {
        "count": 1,
        "refs": [unaccepted_attempt_ref("run-1", "ops")],
    }
    assert "ops" not in json.dumps(exported["unaccepted_attempts"])


def _oversized_tee() -> str:
    """Return complete err lines of exactly the 1 MiB cap plus one byte, then output.

    Reading up to the cap stops on a line boundary, so only the size check
    keeps the output beyond it from being missed.
    """
    empty = json.dumps({"ts": 1, "dir": "err", "b64": ""}) + "\n"
    padding = 1024 * 1024 + 1 - len(empty)
    head = json.dumps({"ts": 1, "dir": "err", "b64": "A" * padding}) + "\n"
    return head + json.dumps({"ts": 2, "dir": "out", "b64": "aWQ="}) + "\n"


@pytest.mark.parametrize(
    "content",
    [
        json.dumps({"ts": 1, "dir": "out", "b64": "aWQ="}) + "\n",
        "not json\n",
        _oversized_tee(),
    ],
    ids=("terminal-output", "malformed-tee", "oversized-tee"),
)
def test_a_census_session_with_possible_output_fails_closed(tmp_path, content):
    """Terminal output in an unaccepted session contradicts never-opened."""
    store_base = _census(tmp_path, "session-1.jsonl")
    (store_base / "run-1/mcp-side/sessions/ops.jsonl").write_text(content)
    backend, _calls = _backend(export={"accepted_session_ids": ["session-1"]})

    exported, failure = export_transcript_payload(
        backend, store_base, "run-1", _BINDING
    )

    assert exported is None
    assert failure == TranscriptExportFailure(
        "unaccepted-output", "census-only 1, with terminal output 1"
    )


def test_a_failed_attempt_ref_is_stable_per_run_and_hides_the_identity():
    """The same session in another run gets a different, non-raw reference."""
    first = unaccepted_attempt_ref("run-1", "ops")

    assert first == unaccepted_attempt_ref("run-1", "ops")
    assert first != unaccepted_attempt_ref("run-2", "ops")
    assert first.startswith("attempt-")
    assert "ops" not in first


def test_a_backend_without_capture_apparatus_fails_at_apparatus(tmp_path):
    """A backend that cannot quiesce or export is named, not swallowed."""
    exported, failure = export_transcript_payload(
        SimpleNamespace(), tmp_path, "run-1", _BINDING
    )

    assert (exported, failure) == (None, TranscriptExportFailure("apparatus"))


def test_an_unquiesced_broker_fails_at_quiesce_before_any_export(tmp_path):
    """No census is read and nothing is exported while admission is open."""
    backend, calls = _backend(quiesced=False, export={})

    exported, failure = export_transcript_payload(
        backend, _census(tmp_path, "session-1.jsonl"), "run-1", _BINDING
    )

    assert (exported, failure) == (None, TranscriptExportFailure("quiesce"))
    assert calls == []


def test_an_invalid_census_fails_at_census_before_any_export(tmp_path):
    """A census entry that is not a session tee stops the export."""
    backend, calls = _backend(export={})

    exported, failure = export_transcript_payload(
        backend, _census(tmp_path, "notes.txt"), "run-1", _BINDING
    )

    assert (exported, failure) == (None, TranscriptExportFailure("census"))
    assert calls == []


def _malformed_export(_expected):
    """Stand in for a broker export that cannot be decoded."""
    raise ValueError("malformed")


@pytest.mark.parametrize(
    "export",
    [None, _malformed_export],
    ids=("no-payload", "malformed-payload"),
)
def test_an_unreadable_broker_export_fails_at_export(tmp_path, export):
    """An export that returns or raises nothing usable is named as the export."""
    backend, _calls = _backend(export=export)

    exported, failure = export_transcript_payload(
        backend, _census(tmp_path, "session-1.jsonl"), "run-1", _BINDING
    )

    assert (exported, failure) == (None, TranscriptExportFailure("export"))


def test_a_reconciliation_mismatch_reports_set_sizes_only(tmp_path):
    """The census and the broker ledger disagree; only their sizes are kept."""

    def mismatch(_expected):
        raise CaptureReconciliationError(
            census=2, accepted=1, census_only=1, broker_only=0
        )

    backend, _calls = _backend(export=mismatch)

    exported, failure = export_transcript_payload(
        backend,
        _census(tmp_path, "session-1.jsonl", "session-2.jsonl"),
        "run-1",
        _BINDING,
    )

    assert exported is None
    assert failure == TranscriptExportFailure(
        "reconciliation",
        "census 2, broker accepted 1, census-only 1, broker-only 0",
    )


def test_the_failure_diagnostic_names_the_step_without_session_identities():
    """The diagnostic carries a fixed code and redacted step text."""
    diagnostic = TranscriptExportFailure(
        "reconciliation", "census 1, broker accepted 0, census-only 1, broker-only 0"
    ).diagnostic()

    assert diagnostic.code == TRANSCRIPT_EXPORT_FAILED
    assert diagnostic.message == (
        "transcript export failed at reconciliation: "
        "census 1, broker accepted 0, census-only 1, broker-only 0"
    )
