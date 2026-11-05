"""Export one full-run transcript at teardown, naming the step that failed."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from raes_contracts.diagnostics import Diagnostic

from aptl.core.deployment.errors import BackendTimeoutError, CaptureReconciliationError
from aptl.core.evidence.outcomes import capture_diagnostic
from aptl.core.experiment.capture_registry import CaptureBinding
from aptl.utils.pathsafe import (
    REASON_NOT_FOUND,
    PathContainmentError,
    listdir_contained_nofollow,
    open_contained_nofollow,
)

TRANSCRIPT_EXPORT_FAILED = "aptl.experiment-capture.transcript-export-failed"


@dataclass(frozen=True)
class TranscriptExportFailure:
    """The export step that left finalization without a payload.

    ``detail`` holds counts only, never session identities or content.
    """

    step: str
    detail: str = ""

    def diagnostic(self) -> Diagnostic:
        """Return the fixed, redacted finalization diagnostic for this failure."""
        suffix = f": {self.detail}" if self.detail else ""
        return capture_diagnostic(
            TRANSCRIPT_EXPORT_FAILED,
            "transcript",
            f"transcript export failed at {self.step}{suffix}",
        )


@dataclass
class _ExportProgress:
    """The step an export attempt reached, read when it fails."""

    step: str = "quiesce"


def expected_transcript_session_ids(
    store_base: Path,
    run_id: str,
    *,
    max_sessions: int,
) -> tuple[str, ...]:
    """Read the MCP-owned expected-session census without following links."""

    relative_dir = f"{run_id}/mcp-side/sessions"
    try:
        names = listdir_contained_nofollow(store_base, relative_dir)
    except PathContainmentError as exc:
        if exc.reason == REASON_NOT_FOUND:
            return ()
        raise
    if len(names) > max_sessions:
        raise ValueError("transcript session census exceeds admitted limits")
    session_ids: list[str] = []
    for name in names:
        if not name.endswith(".jsonl"):
            raise ValueError("unexpected transcript session census entry")
        session_id = name.removesuffix(".jsonl")
        if (
            not session_id
            or session_id.startswith(".")
            or ".." in session_id
            or re.fullmatch(r"\w[\w.-]*", session_id, flags=re.ASCII) is None
        ):
            raise ValueError("invalid transcript session census identity")
        with open_contained_nofollow(store_base, f"{relative_dir}/{name}") as handle:
            # Opening is the check: the census requires a contained regular
            # file, while its content remains owned by the MCP capture path.
            handle.read(0)
        session_ids.append(session_id)
    if len(session_ids) != len(set(session_ids)):
        raise ValueError("duplicate transcript session census identity")
    return tuple(session_ids)


def export_transcript_payload(
    backend: object,
    store_base: Path,
    run_id: str,
    binding: CaptureBinding,
) -> tuple[object | None, TranscriptExportFailure | None]:
    """Quiesce the broker and export against the stable session census.

    Returns the payload, or ``None`` and the step that failed: ``apparatus``,
    ``quiesce``, ``census``, ``export`` or ``reconciliation`` (with set sizes).
    """

    quiesce = getattr(backend, "quiesce_capture_apparatus", None)
    export = getattr(backend, "export_capture_apparatus", None)
    if not callable(quiesce) or not callable(export):
        return None, TranscriptExportFailure("apparatus")
    progress = _ExportProgress()
    try:
        payload = _quiesce_and_export(
            quiesce, export, store_base, run_id, binding, progress
        )
    except CaptureReconciliationError as exc:
        return None, TranscriptExportFailure(
            "reconciliation",
            f"census {exc.census}, broker accepted {exc.accepted}, "
            f"census-only {exc.census_only}, broker-only {exc.broker_only}",
        )
    except (BackendTimeoutError, OSError, PathContainmentError, TypeError, ValueError):
        payload = None
    failure = None if payload is not None else TranscriptExportFailure(progress.step)
    return payload, failure


def _quiesce_and_export(
    quiesce: Callable[[], object],
    export: Callable[..., object],
    store_base: Path,
    run_id: str,
    binding: CaptureBinding,
    progress: _ExportProgress,
) -> object | None:
    """Run the export steps in order, recording each step as it starts."""

    if not quiesce():
        return None
    # Admission is now closed under the broker's registration lock.
    # Read the independent MCP census only after that boundary is stable.
    progress.step = "census"
    expected_session_ids = expected_transcript_session_ids(
        store_base,
        run_id,
        max_sessions=binding.limits.max_artifact_count // 2,
    )
    progress.step = "export"
    return export(expected_session_ids=expected_session_ids)
