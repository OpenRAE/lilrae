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
from typing import IO

from aptl.core.evidence.adapters.sources import (
    CallableWindowedSource,
    SourceResult,
    WindowedSource,
)
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.evidence.spool import JsonArrayWriter, iter_spool, new_spool, spool_size
from aptl.core.runstore import RunStorageBackend
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


def _instant(value: str) -> datetime:
    """Parse a source timestamp and require an explicit time zone."""
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("file timestamp requires a time zone")
    return result


def _select_lines(
    source: IO[bytes],
    target: IO[bytes],
    timestamp_of: Callable[[str], str],
    start: datetime,
    end: datetime,
) -> int:
    """Copy the lines of ``source`` inside ``[start, end]``; return the dropped count."""
    dropped = 0
    pending = b""
    for chunk in [*iter_spool(source), b""]:
        pending += chunk
        lines = pending.splitlines(keepends=True)
        pending = lines.pop() if chunk and lines and not lines[-1].endswith(b"\n") else b""
        for raw in lines:
            line = raw.decode("utf-8", errors="replace")
            try:
                observed = _instant(timestamp_of(line))
            except ValueError, TypeError, KeyError, AttributeError:
                dropped += 1
                continue
            if start <= observed <= end:
                target.write(raw)
    return dropped


@dataclass
class _ReadFlags:
    """Failures observed while streaming native sources."""

    failed: list[dict[str, object] | str] = field(default_factory=list)
    timed_out: bool = False
    interrupted: bool = False

    def status(self, default: CollectorStatus) -> CollectorStatus:
        """Apply the loss-status precedence consistently across native sources."""
        priorities = (
            (self.timed_out, CollectorStatus.TIMEOUT),
            (self.interrupted, CollectorStatus.MID_RUN_LOSS),
            (bool(self.failed), CollectorStatus.SOURCE_UNAVAILABLE),
        )
        return next((status for applies, status in priorities if applies), default)


def _exit_status(exit: object) -> str | None:
    """Return the record status for a streamed read that did not end cleanly."""
    if getattr(exit, "timed_out", False):
        return "timeout"
    if getattr(exit, "failed_pipe", False):
        return "interrupted-read"
    return None


class ContainerFileSource:
    """Read selected files, keeping raw lines within an adapter-decoded window.

    The adapter selects current/rotated paths and decodes each line's timestamp.
    A decoder is required before reading. Each file is streamed completely.
    History gaps, failed files, and malformed lines remain explicit partial
    data.
    """

    def __init__(
        self,
        operations: object,
        files: Sequence[tuple[str, str]],
        *,
        timestamp_of: Callable[[str], str],
    ) -> None:
        self._files = tuple(dict.fromkeys(files))
        for name, path in self._files:
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
        self._operations = operations
        if not callable(timestamp_of):
            raise ValueError("file timestamp decoder is invalid")
        self._timestamp_of = timestamp_of

    def _read_file(
        self,
        name: str,
        path: str,
        window: tuple[datetime, datetime],
        writer: JsonArrayWriter,
        flags: _ReadFlags,
    ) -> int:
        """Stream one admitted file; return the count of undecodable lines."""
        base = {"container": name, "path": path}
        with new_spool() as raw, new_spool() as stderr, new_spool() as selected:
            try:
                exit = self._operations.container_exec_stream(
                    name, ["cat", "--", path], stdout=raw, stderr=stderr
                )
            except TimeoutExpired:
                writer.add({**base, "status": "timeout", "window_coverage": "partial"})
                flags.timed_out = flags.interrupted = True
                return 0
            except Exception:
                writer.add({**base, "status": "source-unavailable"})
                flags.failed.append(base)
                return 0
            status = _exit_status(exit)
            flags.timed_out |= status == "timeout"
            flags.interrupted |= status is not None
            if status is None and exit.returncode:
                status = "source-unavailable"
                flags.failed.append(base)
            dropped = _select_lines(raw, selected, self._timestamp_of, *window)
            fields: dict[str, object] = {
                **base,
                "window_coverage": "partial" if status else "selected-records",
                "coverage_limitations": [
                    "History coverage depends on the adapter-selected current and rotated files."
                ],
            }
            if status:
                fields["status"] = status
            streams = {"output": selected}
            if status in {"timeout", "interrupted-read"} and spool_size(stderr):
                streams["stderr"] = stderr
            writer.add(fields, streams)
            return dropped

    def fetch(self, start_iso: str, end_iso: str) -> SourceResult:
        """Retain selected file lines and disclose gaps and read failures."""
        window = (_instant(start_iso), _instant(end_iso))
        if window[1] < window[0]:
            raise ValueError("file capture window is invalid")
        writer, flags = JsonArrayWriter(), _ReadFlags()
        dropped = 0
        for name, path in self._files:
            dropped += self._read_file(name, path, window, writer, flags)
        return SourceResult(
            status=flags.status(CollectorStatus.MID_RUN_LOSS),
            chunks=writer.finish(),
            dropped_count=dropped,
            source_pipeline={
                "method": "windowed-file-lines",
                "requested_window": [start_iso, end_iso],
                "failed_sources": flags.failed,
            },
        )


class ContainerLogSource:
    """A windowed source over ``DeploymentBackend.container_logs_stream``.

    A non-zero returncode (or a backend error) for any container is a
    ``SOURCE_UNAVAILABLE``. Each captured container's complete output becomes
    one ``{container, output}`` record.
    """

    def __init__(self, backend: object, containers: Sequence[str]) -> None:
        """Bind to a DeploymentBackend and the containers whose logs to capture."""
        self._backend = backend
        self._containers = tuple(containers)

    def _read_container(
        self,
        container: str,
        window: tuple[str, str],
        writer: JsonArrayWriter,
        flags: _ReadFlags,
    ) -> None:
        """Keep each container's read outcome independent of its peers."""
        with new_spool() as output, new_spool() as stderr:
            try:
                exit = self._backend.container_logs_stream(
                    container,
                    since=window[0],
                    until=window[1],
                    stdout=output,
                    stderr=stderr,
                )
            except TimeoutExpired:
                writer.add({"container": container, "status": "timeout"})
                flags.timed_out = True
                return
            except Exception:
                writer.add({"container": container, "status": "source-unavailable"})
                flags.failed.append(container)
                return
            status = _exit_status(exit)
            flags.timed_out |= status == "timeout"
            flags.interrupted |= status == "interrupted-read"
            failed = status is None and exit.returncode != 0
            if failed:
                writer.add({"container": container, "status": "source-unavailable"})
                flags.failed.append(container)
            # A failed command's stderr is its error text, not container data.
            keep_stderr = not failed and spool_size(stderr)
            if not (spool_size(output) or keep_stderr or status):
                return
            fields: dict[str, object] = {"container": container}
            if status:
                fields["status"] = status
            streams = {"output": output}
            if keep_stderr:
                streams["stderr"] = stderr
            writer.add(fields, streams)

    def fetch(self, start_iso: str, end_iso: str) -> SourceResult:
        """Capture each container's window of logs, distinguishing failure from empty."""
        writer, flags = JsonArrayWriter(), _ReadFlags()
        for container in self._containers:
            self._read_container(container, (start_iso, end_iso), writer, flags)
        default = CollectorStatus.OK if writer.count else CollectorStatus.EMPTY_OK
        return SourceResult(
            status=flags.status(default),
            chunks=writer.finish(),
            source_pipeline={
                "requested_sources": list(self._containers),
                "failed_sources": flags.failed,
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
