"""Concrete built-in windowed sources (EXP-010 / issue #752 PR 2).

Each wraps a source owner at the level where the failure signal actually
exists — so a source failure is a distinct
:class:`~aptl.core.evidence.adapters.sources.SourceResult` status, never the
empty-on-error collapse the raw ``collectors.py`` helpers use:

* :class:`RunArchiveSource` — sources already written to the run archive (the
  MCP-side red-activity JSONL, Kali-side harvest): a MISSING subtree is
  ``SOURCE_UNAVAILABLE``, a present-but-empty subtree is ``EMPTY_OK``.
* :class:`ContainerLogSource` — ``DeploymentBackend.container_logs_capture``: a
  non-zero returncode is ``SOURCE_UNAVAILABLE``, empty output is ``EMPTY_OK``.
* :class:`ContainerFileSource` — bounded adapter-selected raw log files read
  through admitted container operations, with explicit truncation/failure rows.
* :func:`soc_windowed_source` — a SOC ``curl_safe`` query whose function
  returns ``None`` on transport failure (distinct from ``[]`` for no events).

Live wiring of these against a running lab is EXECUTION (#437/#459); the source
owners are adapted here, never duplicated or bypassed.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from pathlib import PurePosixPath
from datetime import datetime
from subprocess import TimeoutExpired

from aptl.core.evidence.adapters.sources import (
    CallableWindowedSource,
    SourceResult,
    WindowedSource,
    capture_read_bytes,
)
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.runstore import RunStorageBackend
from aptl.utils.redaction import redact
from aptl.utils.pathsafe import (
    PathContainmentError,
    open_contained_nofollow,
    open_dir_contained_nofollow,
)
from aptl.utils.probe_execution import probe_output_byte_limit


class RunArchiveSource:
    """A windowed source reading run-scoped JSONL already written to the archive.

    The subtree ``<run_id>/<subdir>/`` is enumerated for ``*.jsonl`` files;
    each valid JSON line is one record. A missing subtree means the source
    never wrote (``SOURCE_UNAVAILABLE``); an empty one means it ran and
    produced nothing (``EMPTY_OK``). Malformed lines are dropped and counted so
    the loss is disclosed, never silently swallowed.
    """

    def __init__(self, run_store: RunStorageBackend, run_id: str, subdir: str) -> None:
        """Bind to a run store, run id, and the archive subtree to read."""
        self._run_store = run_store
        self._run_id = run_id
        self._subdir = subdir

    def fetch(self, start_iso: str, end_iso: str) -> SourceResult:
        """Read the subtree's JSONL records (the window is the run's own scope)."""
        # The archive subtree is already run-scoped, so the window is unused.
        del start_iso, end_iso
        return self._read_subtree()

    def check_readiness(self, _at_iso: str) -> bool:
        """Verify bounded archive reads without invoking capture acquisition."""
        result = self._read_subtree()
        return (
            result.status in {CollectorStatus.OK, CollectorStatus.EMPTY_OK}
            and result.dropped_count == 0
        )

    def _archive_subtree(self) -> tuple[Path, Path]:
        """Require the selected run directory and refuse linked ancestors."""
        try:
            root = self._run_store.get_run_path(self._run_id)
            subtree = root / self._subdir
            directory = open_dir_contained_nofollow(root, Path(self._subdir))
            os.close(directory)
            if not subtree.is_dir():
                raise OSError("archive-subtree-unavailable")
        except Exception:
            raise OSError("archive-subtree-unavailable") from None
        return root, subtree

    def _read_subtree(self) -> SourceResult:
        try:
            root, subtree = self._archive_subtree()
            records, dropped = _read_jsonl_tree(
                subtree, root=root, byte_limit=probe_output_byte_limit()
            )
        except OverflowError:
            return SourceResult(status=CollectorStatus.TRUNCATION)
        except OSError, ValueError, PathContainmentError:
            return SourceResult(status=CollectorStatus.SOURCE_UNAVAILABLE)
        status = CollectorStatus.OK if records else CollectorStatus.EMPTY_OK
        return SourceResult(status=status, records=records, dropped_count=dropped)


def _partial_read_record(name: str, exc: Exception) -> dict[str, object]:
    def text(value: object) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value if isinstance(value, str) else ""

    return {
        "container": name,
        "status": "timeout" if isinstance(exc, TimeoutExpired) else "interrupted-read",
        "output": text(getattr(exc, "stdout", None)),
        "stderr": text(getattr(exc, "stderr", None)),
        "window_coverage": "partial",
    }


def _select_file_window(
    records: list[dict[str, object]],
    timestamp_of: Callable[[str], str],
    start_iso: str,
    end_iso: str,
) -> int:
    """Select complete raw lines by an adapter-owned timestamp decoder."""

    def instant(value: str) -> datetime:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError("file timestamp requires a time zone")
        return result

    start, end = instant(start_iso), instant(end_iso)
    if end < start:
        raise ValueError("file capture window is invalid")
    dropped = 0
    for record in records:
        selected = []
        for line in record.get("output", "").splitlines(keepends=True):
            try:
                observed = instant(timestamp_of(line))
            except ValueError, TypeError, KeyError, AttributeError:
                dropped += 1
                continue
            if start <= observed <= end:
                selected.append(line)
        record["output"] = "".join(selected)
        record["window_coverage"] = "selected-records"
        record["coverage_limitations"] = [
            "History coverage depends on the adapter-selected current and rotated files."
        ]
    return dropped


class ContainerFileSource:
    """Read selected files, keeping raw lines within an adapter-decoded window.

    The adapter selects current/rotated paths and decodes each line's timestamp.
    A decoder is required before reading. History gaps, failed files,
    malformed lines and bounded reads remain explicit partial data.
    """

    def __init__(
        self,
        operations: object,
        files: Sequence[tuple[str, str]],
        *,
        max_bytes: int = 1024 * 1024,
        timestamp_of: Callable[[str], str],
    ) -> None:
        if type(max_bytes) is not int or not 1 <= max_bytes <= 8 * 1024 * 1024:
            raise ValueError("log file byte limit is invalid")
        self._files = tuple(dict.fromkeys(files))
        if len(self._files) > 256:
            raise ValueError("too many log file sources")
        for name, path in self._files:
            if (
                not name
                or len(name) > 128
                or len(path) > 4096
                or not PurePosixPath(path).is_absolute()
                or ".." in PurePosixPath(path).parts
                or "\0" in path
            ):
                raise ValueError("log file source is invalid")
        self._operations, self._limit = operations, max_bytes
        if not callable(timestamp_of):
            raise ValueError("file timestamp decoder is invalid")
        self._timestamp_of = timestamp_of

    def fetch(self, start_iso: str, end_iso: str) -> SourceResult:
        records, failed = [], []
        remaining, truncated, timed_out, interrupted = self._limit, False, False, False
        for index, (name, path) in enumerate(self._files):
            if remaining <= 0:
                truncated = True
                records.extend(
                    {"container": name, "path": path, "status": "not-read-byte-limit"}
                    for name, path in self._files[index:]
                )
                break
            try:
                result = self._operations.container_exec(
                    name, ["head", "-c", str(remaining + 1), "--", path], timeout=30
                )
                if result.returncode:
                    failed.append({"container": name, "path": path})
                raw = result.stdout.encode("utf-8")
                truncated |= len(raw) > remaining
                retained = raw[:remaining].decode("utf-8", errors="ignore")
                remaining -= len(raw[:remaining])
                records.append(
                    {
                        "container": name,
                        "path": path,
                        "output": retained,
                        "truncated": len(raw) > len(retained.encode("utf-8")),
                        **(
                            {"status": "source-unavailable"}
                            if result.returncode
                            else {}
                        ),
                    }
                )
            except (TimeoutExpired, InterruptedError) as exc:
                record = _partial_read_record(name, exc)
                record["path"] = path
                # Preserve accepted streams within the same raw read budget.
                for key in ("output", "stderr"):
                    raw = record[key].encode("utf-8")
                    truncated |= len(raw) > remaining
                    record[key] = raw[:remaining].decode("utf-8", errors="ignore")
                    remaining -= min(len(raw), remaining)
                records.append(record)
                timed_out |= isinstance(exc, TimeoutExpired)
                interrupted = True
            except Exception:
                failed.append({"container": name, "path": path})
                records.append(
                    {"container": name, "path": path, "status": "source-unavailable"}
                )
        status = (
            CollectorStatus.TRUNCATION
            if truncated
            else CollectorStatus.TIMEOUT
            if timed_out
            else CollectorStatus.MID_RUN_LOSS
            if interrupted
            else CollectorStatus.SOURCE_UNAVAILABLE
            if failed
            else CollectorStatus.MID_RUN_LOSS
        )
        for row in records:
            row["requested_window"] = [start_iso, end_iso]
        dropped = _select_file_window(records, self._timestamp_of, start_iso, end_iso)
        return SourceResult(
            status=status,
            records=records,
            dropped_count=dropped,
            source_pipeline={
                "method": "windowed-file-lines",
                "requested_window": [start_iso, end_iso],
                "failed_sources": failed,
                "truncated": truncated,
            },
        )


class ContainerLogSource:
    """A windowed source over ``DeploymentBackend.container_logs_capture``.

    A non-zero returncode (or a backend error) for any container is a
    ``SOURCE_UNAVAILABLE`` — the returncode is the distinct failure signal the
    raw ``collect_container_logs`` helper discards. Each captured container's
    output becomes one ``{container, output}`` record.
    """

    def __init__(
        self,
        backend: object,
        containers: Sequence[str],
        *,
        max_bytes: int = 1024 * 1024,
    ) -> None:
        """Bind to a DeploymentBackend and the containers whose logs to capture."""
        self._backend = backend
        self._containers = tuple(containers)
        if type(max_bytes) is not int or not 1024 <= max_bytes <= 8 * 1024 * 1024:
            raise ValueError("log capture byte limit is invalid")
        self._limit = max_bytes

    def fetch(self, start_iso: str, end_iso: str) -> SourceResult:
        """Capture each container's window of logs, distinguishing failure from empty."""
        records: list[dict[str, object]] = []
        failed: list[str] = []
        timed_out, interrupted, truncated = False, False, False
        budget = min(
            capture_read_bytes(self._limit), probe_output_byte_limit() or self._limit
        )
        per_source = max(
            1,
            (budget - 512 * len(self._containers)) // max(1, 6 * len(self._containers)),
        )
        for container in self._containers:
            try:
                result = self._backend.container_logs_capture(
                    container,
                    since=start_iso,
                    until=end_iso,
                    timeout=30,
                    max_bytes=per_source,
                )
            except (TimeoutExpired, InterruptedError) as exc:
                records.append(_partial_read_record(container, exc))
                timed_out |= isinstance(exc, TimeoutExpired)
                interrupted = True
                failed.append(container)
                continue
            except Exception:
                failed.append(container)
                records.append({"container": container, "status": "source-unavailable"})
                continue
            read_truncated = getattr(result, "truncated", False) is True
            read_timed_out = getattr(result, "timed_out", False) is True
            truncated |= read_truncated
            timed_out |= read_timed_out
            if result.returncode != 0 and not (read_truncated or read_timed_out):
                failed.append(container)
                records.append({"container": container, "status": "source-unavailable"})
            output = result.stdout or ""
            # Docker puts the container's stderr on stderr too. On failure,
            # stderr is a transport diagnostic, so keep only accepted stdout.
            stderr = (
                (result.stderr or "")
                if result.returncode == 0 or read_truncated or read_timed_out
                else ""
            )
            if output or stderr or read_truncated or read_timed_out:
                record = {"container": container, "output": output}
                if read_truncated or read_timed_out:
                    record["status"] = "truncation" if read_truncated else "timeout"
                if stderr:
                    record["stderr"] = stderr
                records.append(record)
        for record in records:
            # Alternate native backends must also fit the admitted source budget.
            # Redact complete values before retaining a prefix.
            for key in ("output", "stderr"):
                value = record.get(key)
                if isinstance(value, str) and len(value.encode("utf-8")) > per_source:
                    safe = redact(value).encode("utf-8")
                    record[key] = safe[:per_source].decode("utf-8", errors="ignore")
                    record["truncated"] = True
                    truncated = True
        status = (
            CollectorStatus.TRUNCATION
            if truncated
            else CollectorStatus.TIMEOUT
            if timed_out
            else CollectorStatus.MID_RUN_LOSS
            if interrupted
            else CollectorStatus.SOURCE_UNAVAILABLE
            if failed
            else CollectorStatus.OK
            if records
            else CollectorStatus.EMPTY_OK
        )
        return SourceResult(
            status=status,
            records=records,
            source_pipeline={
                "requested_sources": list(self._containers),
                "failed_sources": failed,
            },
        )


def soc_windowed_source(
    query: Callable[[str, str], list[dict[str, object]] | None],
    *,
    readiness: Callable[[str], bool] | None = None,
) -> WindowedSource:
    """Adapt a SOC query returning ``list`` (events) or ``None`` (transport failure).

    ``None`` — what the ``curl_safe`` boundary returns on an HTTP/transport
    error — is mapped to ``SOURCE_UNAVAILABLE`` (distinct from ``[]`` for no
    events); the query is never called for its executable identity.
    """

    def _fetch(start_iso: str, end_iso: str) -> SourceResult:
        """Run the SOC query, mapping ``None`` (transport failure) to unavailable."""
        result = query(start_iso, end_iso)
        if result is None:
            return SourceResult(status=CollectorStatus.SOURCE_UNAVAILABLE)
        status = CollectorStatus.OK if result else CollectorStatus.EMPTY_OK
        return SourceResult(status=status, records=list(result))

    return CallableWindowedSource(_fetch, readiness=readiness)


def _read_jsonl_tree(
    subtree: Path, *, root: Path, byte_limit: int | None
) -> tuple[list[dict[str, object]], int]:
    """Stream JSONL with one acquisition budget across all selected files."""
    records: list[dict[str, object]] = []
    dropped = 0
    remaining = byte_limit
    for path in subtree.rglob("*.jsonl"):
        if not path.is_file():
            continue
        payload, remaining = _read_jsonl_payload(root, path, remaining)
        for line in payload.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped.decode("utf-8", errors="replace")))
            except json.JSONDecodeError:
                dropped += 1
    return records, dropped


def _read_jsonl_payload(
    root: Path, path: Path, remaining: int | None
) -> tuple[bytearray, int | None]:
    """Cap each raw file read against the remaining shared acquisition budget."""
    payload = bytearray()
    with open_contained_nofollow(root, path.relative_to(root)) as source:
        while True:
            # read1 bounds raw acquisition; buffered readline may read ahead.
            size = 8192 if remaining is None else min(8192, remaining + 1)
            chunk = source.read1(size)
            if remaining is not None:
                remaining -= len(chunk)
                if remaining < 0:
                    raise OverflowError("source-byte-limit")
            if not chunk:
                break
            payload.extend(chunk)
    return payload, remaining
