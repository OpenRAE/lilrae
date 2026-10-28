"""Export one full-run transcript at teardown, naming the step that failed.

The MCP creates a census entry before each SSH request; the broker records a
session only when it accepts it, before it spawns the inner shell. A census
entry the broker never accepted therefore ran nothing on Kali through the
broker. Such an entry is excluded as a failed attempt when its tee holds no
terminal output; terminal output there is contradictory and fails closed.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from raes_contracts.diagnostics import Diagnostic

from aptl.core.deployment.errors import CaptureReconciliationError
from aptl.core.evidence.outcomes import capture_diagnostic
from aptl.core.experiment.capture_registry import CaptureBinding
from aptl.utils.pathsafe import (
    REASON_NOT_FOUND,
    PathContainmentError,
    listdir_contained_nofollow,
    open_contained_nofollow,
)

TRANSCRIPT_EXPORT_FAILED = "aptl.experiment-capture.transcript-export-failed"
_MAX_ATTEMPT_TEE_BYTES = 1024 * 1024
_ATTEMPT_REF_DOMAIN = b"aptl.transcript.unaccepted-attempt/v1\0"


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
    census: tuple[str, ...] = ()


def unaccepted_attempt_ref(run_id: str, session_id: str) -> str:
    """Return the stable reference recorded for one failed session attempt.

    The session identity is hashed with the run, so no raw identity is kept.
    """
    digest = hashlib.sha256(
        _ATTEMPT_REF_DOMAIN + run_id.encode() + b"\0" + session_id.encode()
    )
    return "attempt-" + digest.hexdigest()


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
    ``quiesce``, ``census``, ``export``, ``reconciliation`` (with set sizes) or
    ``unaccepted-output``. The returned payload's ``expected_session_ids`` are
    the accepted sessions, and ``unaccepted_attempts`` records the rest.
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
    except (OSError, PathContainmentError, TypeError, ValueError):
        payload = None
    return (
        _exclude_unaccepted_attempts(payload, store_base, run_id, progress.census)
        if payload is not None
        else (None, TranscriptExportFailure(progress.step))
    )


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
    progress.census = expected_transcript_session_ids(
        store_base,
        run_id,
        max_sessions=binding.limits.max_artifact_count // 2,
    )
    progress.step = "export"
    return export(expected_session_ids=progress.census)


def _exclude_unaccepted_attempts(
    payload: object,
    store_base: Path,
    run_id: str,
    census: Sequence[str],
) -> tuple[object | None, TranscriptExportFailure | None]:
    """Keep the accepted sessions and record the census-only ones as attempts."""

    accepted_raw = (
        payload.get("accepted_session_ids") if isinstance(payload, Mapping) else None
    )
    if not isinstance(accepted_raw, list):
        return None, TranscriptExportFailure("export")
    accepted = set(accepted_raw)
    unaccepted = [session_id for session_id in census if session_id not in accepted]
    with_output = sum(
        _tee_has_terminal_output(store_base, run_id, session_id)
        for session_id in unaccepted
    )
    if with_output:
        return None, TranscriptExportFailure(
            "unaccepted-output",
            f"census-only {len(unaccepted)}, with terminal output {with_output}",
        )
    attempts = {
        "count": len(unaccepted),
        "refs": sorted(unaccepted_attempt_ref(run_id, item) for item in unaccepted),
    }
    expected = [session_id for session_id in census if session_id in accepted]
    return {
        **payload,
        "expected_session_ids": expected,
        "unaccepted_attempts": attempts,
    }, None


def _tee_has_terminal_output(store_base: Path, run_id: str, session_id: str) -> bool:
    """Return whether a census tee may hold terminal output, failing closed.

    Only ``err`` records (a refusal or SSH error) or an empty tee count as a
    session that never opened. Any other record, or an unreadable, oversized
    or malformed tee, counts as output.
    """

    relative = f"{run_id}/mcp-side/sessions/{session_id}.jsonl"
    try:
        with open_contained_nofollow(store_base, relative) as handle:
            data = handle.read(_MAX_ATTEMPT_TEE_BYTES + 1)
        records = [json.loads(line) for line in data.splitlines() if line.strip()]
    except (OSError, PathContainmentError, ValueError):
        return True
    return len(data) > _MAX_ATTEMPT_TEE_BYTES or any(
        not isinstance(record, Mapping) or record.get("dir") != "err"
        for record in records
    )
