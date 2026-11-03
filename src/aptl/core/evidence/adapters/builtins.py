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

from aptl.core.evidence.adapters.sources import (
    CallableWindowedSource,
    SourceResult,
    WindowedSource,
)
from aptl.core.evidence.outcomes import CollectorStatus
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

    def _read_subtree(self) -> SourceResult:
        try:
            root = self._run_store.get_run_path(self._run_id)
            subtree = root / self._subdir
            directory = open_dir_contained_nofollow(root, Path(self._subdir))
            os.close(directory)
        except Exception:
            return SourceResult(status=CollectorStatus.SOURCE_UNAVAILABLE)
        if not subtree.is_dir():
            return SourceResult(status=CollectorStatus.SOURCE_UNAVAILABLE)
        try:
            records, dropped = _read_jsonl_tree(
                subtree, root=root, byte_limit=probe_output_byte_limit()
            )
        except OverflowError:
            return SourceResult(status=CollectorStatus.TRUNCATION)
        except OSError, ValueError, PathContainmentError:
            return SourceResult(status=CollectorStatus.SOURCE_UNAVAILABLE)
        status = CollectorStatus.OK if records else CollectorStatus.EMPTY_OK
        return SourceResult(status=status, records=records, dropped_count=dropped)


class ContainerLogSource:
    """A windowed source over ``DeploymentBackend.container_logs_capture``.

    A non-zero returncode (or a backend error) for any container is a
    ``SOURCE_UNAVAILABLE`` — the returncode is the distinct failure signal the
    raw ``collect_container_logs`` helper discards. Each captured container's
    output becomes one ``{container, output}`` record.
    """

    def __init__(self, backend: object, containers: Sequence[str]) -> None:
        """Bind to a DeploymentBackend and the containers whose logs to capture."""
        self._backend = backend
        self._containers = tuple(containers)

    def fetch(self, start_iso: str, end_iso: str) -> SourceResult:
        """Capture each container's window of logs, distinguishing failure from empty."""
        records: list[dict[str, object]] = []
        remaining = probe_output_byte_limit()
        for container in self._containers:
            try:
                result = self._backend.container_logs_capture(
                    container, since=start_iso, until=end_iso, timeout=30
                )
            except Exception:
                return SourceResult(status=CollectorStatus.SOURCE_UNAVAILABLE)
            if result.returncode != 0:
                return SourceResult(status=CollectorStatus.SOURCE_UNAVAILABLE)
            output = (result.stdout or "").strip()
            if remaining is not None:
                remaining -= len(output.encode("utf-8"))
                if remaining < 0:
                    return SourceResult(status=CollectorStatus.TRUNCATION)
            if output:
                records.append({"container": container, "output": output})
        status = CollectorStatus.OK if records else CollectorStatus.EMPTY_OK
        return SourceResult(status=status, records=records)


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
        payload = bytearray()
        with open_contained_nofollow(root, path.relative_to(root)) as source:
            while True:
                # read1 bounds the raw acquisition too; buffered readline can
                # read ahead past the requested line length.
                size = 8192 if remaining is None else min(8192, remaining + 1)
                chunk = source.read1(size)
                if remaining is not None:
                    remaining -= len(chunk)
                    if remaining < 0:
                        raise OverflowError("source-byte-limit")
                if not chunk:
                    break
                payload.extend(chunk)
        for line in payload.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped.decode("utf-8", errors="replace")))
            except json.JSONDecodeError:
                dropped += 1
    return records, dropped
