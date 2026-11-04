"""Built-in archive, native log/file, and SOC sources.

Keep source failures distinct from successful empty reads. Selected adapters
own source choice; shared collectors own acquisition and retained artifacts.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from pathlib import PurePosixPath
from dataclasses import dataclass, field
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
    """Retain accepted streams from an interrupted source read."""

    def text(value: object) -> str:
        """Decode accepted source output without exposing exception diagnostics."""
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
        """Parse a source timestamp and require an explicit time zone."""
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


@dataclass
class _ReadResult:
    """Accepted native rows and the limits or failures observed while reading them."""

    records: list[dict[str, object]] = field(default_factory=list)
    consumed_bytes: int = 0
    failed: bool = False
    truncated: bool = False
    timed_out: bool = False
    interrupted: bool = False

    def add(self, other: _ReadResult) -> None:
        """Accumulate accepted rows without losing a peer's failure or limit flags."""
        self.records.extend(other.records)
        self.consumed_bytes += other.consumed_bytes
        self.failed |= other.failed
        self.truncated |= other.truncated
        self.timed_out |= other.timed_out
        self.interrupted |= other.interrupted


def _read_status(result: _ReadResult, default: CollectorStatus) -> CollectorStatus:
    """Apply the existing loss-status precedence consistently across native sources."""
    priorities = (
        (result.truncated, CollectorStatus.TRUNCATION),
        (result.timed_out, CollectorStatus.TIMEOUT),
        (result.interrupted, CollectorStatus.MID_RUN_LOSS),
        (result.failed, CollectorStatus.SOURCE_UNAVAILABLE),
    )
    return next((status for applies, status in priorities if applies), default)


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
            if not name:
                raise ValueError("log file source is invalid")
            if not all(
                (
                    name,
                    len(name) <= 128,
                    len(path) <= 4096,
                    PurePosixPath(path).is_absolute(),
                    ".." not in PurePosixPath(path).parts,
                    "\0" not in path,
                )
            ):
                raise ValueError("log file source is invalid")
        self._operations, self._limit = operations, max_bytes
        if not callable(timestamp_of):
            raise ValueError("file timestamp decoder is invalid")
        self._timestamp_of = timestamp_of

    @staticmethod
    def _partial_file(
        name: str, path: str, remaining: int, exc: Exception
    ) -> _ReadResult:
        """Keep accepted streams from an interrupted file read within the shared quota."""
        record = {**_partial_read_record(name, exc), "path": path}
        result = _ReadResult(
            records=[record],
            timed_out=isinstance(exc, TimeoutExpired),
            interrupted=True,
        )
        for key in ("output", "stderr"):
            raw = record[key].encode("utf-8")
            result.truncated |= len(raw) > remaining
            record[key] = raw[:remaining].decode("utf-8", errors="ignore")
            consumed = min(len(raw), remaining)
            result.consumed_bytes += consumed
            remaining -= consumed
        return result

    def _read_file(self, name: str, path: str, remaining: int) -> _ReadResult:
        """Read one admitted file while preserving failed and interrupted source data."""
        try:
            result = self._operations.container_exec(
                name, ["head", "-c", str(remaining + 1), "--", path], timeout=30
            )
            return self._file_result(name, path, remaining, result)
        except (TimeoutExpired, InterruptedError) as exc:
            return self._partial_file(name, path, remaining, exc)
        except Exception:
            return _ReadResult(
                records=[
                    {"container": name, "path": path, "status": "source-unavailable"}
                ],
                failed=True,
            )

    @staticmethod
    def _file_result(
        name: str, path: str, remaining: int, result: object
    ) -> _ReadResult:
        """Retain raw bytes from one file without exceeding its remaining source share."""
        raw = result.stdout.encode("utf-8")
        retained = raw[:remaining].decode("utf-8", errors="ignore")
        record = {
            "container": name,
            "path": path,
            "output": retained,
            "truncated": len(raw) > len(retained.encode("utf-8")),
        }
        if result.returncode:
            record["status"] = "source-unavailable"
        return _ReadResult(
            records=[record],
            consumed_bytes=min(len(raw), remaining),
            failed=bool(result.returncode),
            truncated=len(raw) > remaining,
        )

    def fetch(self, start_iso: str, end_iso: str) -> SourceResult:
        """Retain selected file lines and disclose gaps, read failures, and byte limits."""
        collected, failed = _ReadResult(), []
        remaining = self._limit
        for index, (name, path) in enumerate(self._files):
            if remaining <= 0:
                collected.truncated = True
                collected.records.extend(
                    {"container": name, "path": path, "status": "not-read-byte-limit"}
                    for name, path in self._files[index:]
                )
                break
            result = self._read_file(name, path, remaining)
            collected.add(result)
            remaining -= result.consumed_bytes
            if result.failed:
                failed.append({"container": name, "path": path})
        for row in collected.records:
            row["requested_window"] = [start_iso, end_iso]
        dropped = _select_file_window(
            collected.records, self._timestamp_of, start_iso, end_iso
        )
        return SourceResult(
            status=_read_status(collected, CollectorStatus.MID_RUN_LOSS),
            records=collected.records,
            dropped_count=dropped,
            source_pipeline={
                "method": "windowed-file-lines",
                "requested_window": [start_iso, end_iso],
                "failed_sources": failed,
                "truncated": collected.truncated,
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

    def _read_container(
        self, container: str, start: str, end: str, limit: int
    ) -> _ReadResult:
        """Keep each container's read outcome independent of its peers."""
        try:
            result = self._backend.container_logs_capture(
                container, since=start, until=end, timeout=30, max_bytes=limit
            )
        except (TimeoutExpired, InterruptedError) as exc:
            return _ReadResult(
                records=[_partial_read_record(container, exc)],
                failed=True,
                timed_out=isinstance(exc, TimeoutExpired),
                interrupted=True,
            )
        except Exception:
            return _ReadResult(
                records=[{"container": container, "status": "source-unavailable"}],
                failed=True,
            )
        return _log_result(container, result)

    def fetch(self, start_iso: str, end_iso: str) -> SourceResult:
        """Capture each container's window of logs, distinguishing failure from empty."""
        collected, failed = _ReadResult(), []
        budget = min(
            capture_read_bytes(self._limit), probe_output_byte_limit() or self._limit
        )
        per_source = max(
            1,
            (budget - 512 * len(self._containers)) // max(1, 6 * len(self._containers)),
        )
        for container in self._containers:
            result = self._read_container(container, start_iso, end_iso, per_source)
            collected.add(result)
            if result.failed:
                failed.append(container)
        _limit_log_records(collected, per_source)
        default = CollectorStatus.OK if collected.records else CollectorStatus.EMPTY_OK
        return SourceResult(
            status=_read_status(collected, default),
            records=collected.records,
            source_pipeline={
                "requested_sources": list(self._containers),
                "failed_sources": failed,
            },
        )


def _log_output(
    container: str, result: object, truncated: bool, timed_out: bool
) -> list[dict[str, object]]:
    """Keep stderr as container data only after success or an accepted bounded read."""
    output = result.stdout or ""
    stderr = (
        (result.stderr or "")
        if any((result.returncode == 0, truncated, timed_out))
        else ""
    )
    records = []
    if any((output, stderr, truncated, timed_out)):
        record = {"container": container, "output": output}
        if truncated or timed_out:
            record["status"] = "truncation" if truncated else "timeout"
        if stderr:
            record["stderr"] = stderr
        records.append(record)
    return records


def _log_result(container: str, result: object) -> _ReadResult:
    """Translate native stream flags without hiding accepted partial stdout."""
    truncated = getattr(result, "truncated", False) is True
    timed_out = getattr(result, "timed_out", False) is True
    failed = result.returncode != 0 and not any((truncated, timed_out))
    records = (
        [{"container": container, "status": "source-unavailable"}] if failed else []
    )
    records.extend(_log_output(container, result, truncated, timed_out))
    return _ReadResult(
        records=records, failed=failed, truncated=truncated, timed_out=timed_out
    )


def _limit_log_records(result: _ReadResult, per_source: int) -> None:
    """Redact complete values before bounding alternate backend output to its source share."""
    for record in result.records:
        for key in ("output", "stderr"):
            value = record.get(key)
            if isinstance(value, str) and len(value.encode("utf-8")) > per_source:
                safe = redact(value).encode("utf-8")
                record[key] = safe[:per_source].decode("utf-8", errors="ignore")
                record["truncated"] = True
                result.truncated = True


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
