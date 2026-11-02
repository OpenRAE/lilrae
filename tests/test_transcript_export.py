"""The teardown transcript export names the step that left it without a payload."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from aptl.backends._raes_transcript_export import (
    TRANSCRIPT_EXPORT_FAILED,
    TranscriptExportFailure,
    export_transcript_payload,
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


def test_a_matching_export_returns_its_payload_and_no_failure(tmp_path):
    """A reconciled export passes through unchanged."""
    payload = {"accepted_session_ids": ["session-1"]}
    backend, calls = _backend(export=payload)

    exported, failure = export_transcript_payload(
        backend, _census(tmp_path, "session-1.jsonl"), "run-1", _BINDING
    )

    assert (exported, failure) == (payload, None)
    assert calls == [("session-1",)]


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
