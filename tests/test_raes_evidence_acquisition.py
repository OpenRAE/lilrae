"""Native evidence acquisition and transcript failure handling at the lab boundary."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from aptl.core.evidence.adapters.sources import SourceResult
from aptl.core.evidence.outcomes import AcquisitionDisposition, CollectorStatus
from aptl.utils.pathsafe import PathContainmentError


class _SequenceClock:
    def __init__(self, *values: str) -> None:
        self._values = iter(values)

    def now(self) -> str:
        return next(self._values)

    def clock_context(self, **_kwargs):  # pragma: no cover - protocol-only seam
        raise NotImplementedError


@dataclass
class _Source:
    result: SourceResult
    window: tuple[str, str] | None = None

    def fetch(self, start_iso: str, end_iso: str) -> SourceResult:
        self.window = (start_iso, end_iso)
        return self.result


def test_native_failure_messages_expose_codes_not_evidence_payloads():
    from aptl.core.lab import _native_capture_failure, _native_evaluation_failure

    capture = SimpleNamespace(
        reports=(
            SimpleNamespace(
                registration_id="aptl.collector.wazuh-agent-readiness",
                status=CollectorStatus.SOURCE_UNAVAILABLE,
                diagnostic_code="not-ready",
                payload="secret-body",
            ),
        )
    )
    refresh = SimpleNamespace(
        diagnostics=(
            SimpleNamespace(
                code="aptl.evaluator.native-evidence-truth-incomplete",
                message="secret-body",
            ),
        )
    )

    capture_error = _native_capture_failure(capture)
    evaluation_error = _native_evaluation_failure(refresh)

    assert "wazuh-agent-readiness=source-unavailable" in capture_error
    assert "aptl.evaluator.native-evidence-truth-incomplete" in evaluation_error
    assert "secret-body" not in capture_error + evaluation_error


def test_expected_transcript_sessions_come_from_sorted_mcp_census(tmp_path):
    from aptl.backends._raes_transcript_export import (
        expected_transcript_session_ids,
    )

    census = tmp_path / "run-1/mcp-side/sessions"
    census.mkdir(parents=True)
    (census / "session-b.jsonl").write_text("")
    (census / "session-a.jsonl").write_text("")

    assert expected_transcript_session_ids(
        tmp_path,
        "run-1",
        max_sessions=10,
    ) == ("session-a", "session-b")


def test_expected_transcript_sessions_reject_symlinked_census_entry(tmp_path):
    from aptl.backends._raes_transcript_export import (
        expected_transcript_session_ids,
    )

    census = tmp_path / "run-1/mcp-side/sessions"
    census.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_text("not a census record")
    (census / "session-a.jsonl").symlink_to(outside)

    with pytest.raises(PathContainmentError):
        expected_transcript_session_ids(
            tmp_path,
            "run-1",
            max_sessions=10,
        )


def _exported_session(*, session_id="session-1", frames=()):
    return {
        "session_id": session_id,
        "started_at": "2026-09-14T10:00:01Z",
        "finished_at": "2026-09-14T10:00:02Z",
        "close_reason": "clean-exit",
        "loss_count": 0,
        "final_chain_digest": "sha256:" + "00" * 32,
        "frames": list(frames),
    }


@pytest.mark.parametrize("raises", [False, True], ids=("failed-result", "exception"))
def test_lab_stop_passes_the_failed_result_to_the_failure_marker(
    tmp_path, monkeypatch, raises
):
    """The marker gets the result's diagnostics, or none when finalization raised."""
    from aptl.backends import raes_evidence_acquisition as acquisition
    from aptl.core import lab

    failed = SimpleNamespace(disposition=AcquisitionDisposition.INCONCLUSIVE)
    state = {"run_id": "run-1"}
    marked = []

    def finalize(**_kwargs):
        if raises:
            raise ValueError("finalization failed")
        return failed

    monkeypatch.setattr(
        acquisition, "load_active_transcript_authorities", lambda _project: (state,)
    )
    monkeypatch.setattr(acquisition, "finalize_active_transcript_authority", finalize)
    monkeypatch.setattr(
        acquisition,
        "mark_transcript_finalization_failed",
        lambda **kwargs: marked.append(kwargs),
    )
    monkeypatch.setattr(lab, "_expected_transcript_store", lambda _project: tmp_path)

    result = lab._finalize_required_transcript_capture(tmp_path, object())

    assert result.error == (
        "aptl.scenario-evidence.required-transcript-finalization-failed"
    )
    assert marked == [
        {"project_dir": tmp_path, "state": state, "result": None if raises else failed}
    ]


def test_lab_stop_still_tears_down_when_required_transcript_finalization_fails(
    tmp_path, monkeypatch
):
    from aptl.core import lab
    from aptl.core.lab_types import LabResult

    stopped = []
    backend = SimpleNamespace(
        stop=lambda profiles, remove_volumes: (
            stopped.append((profiles, remove_volumes)) or LabResult(success=True)
        )
    )
    monkeypatch.setattr(
        lab,
        "_finalize_required_transcript_capture",
        lambda _project, _backend: LabResult(
            success=False,
            error="aptl.scenario-evidence.required-transcript-finalization-failed",
        ),
    )

    result = lab._stop_lab_owned(True, tmp_path, backend)

    assert stopped
    assert stopped[0][1] is True
    assert result.success is False
    assert (
        result.error == "aptl.scenario-evidence.required-transcript-finalization-failed"
    )
