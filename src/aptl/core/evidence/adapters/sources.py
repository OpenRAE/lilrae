"""Windowed-query collector framework for trusted built-in sources (EXP-010 /
issue #752 preflight "Narrow collector boundary").

Most APTL evidence sources are windowed queries: given the trial's start/stop
observation window, return the events in it. :class:`WindowedQueryCollector`
is the one generic :class:`~aptl.core.evidence.protocol.Collector` for all of
them — it stamps the window from the injected clock, calls a narrow
:class:`WindowedSource`, and maps the source's typed
:class:`SourceResult` onto a :class:`~aptl.core.evidence.protocol.
CollectorOutcome`. A source reports OK / legitimately-empty / a distinct
failure — the empty-on-error collapse of ``collectors.py`` is never allowed to
read as success.

A :class:`WindowedSource` is the ONLY thing a collector talks to; it wraps a
source owner (``DeploymentBackend``, a SOC ``curl_safe`` client, the run
archive) at the level where the failure signal exists, and is injected by
trusted composition code — never selected by experiment input.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from contextvars import ContextVar
from subprocess import TimeoutExpired
from time import monotonic
from typing import Protocol, runtime_checkable

from aptl.core.correlation.clock import ClockProvider
from aptl.core.evidence.outcomes import SUCCESS_STATUSES, CollectorStatus
from aptl.core.deployment._cleanup_budget import (
    cleanup_command_timeout,
    native_read_budget,
)
from aptl.core.deployment.errors import BackendTimeoutError
from aptl.core.evidence.protocol import CollectorContext, CollectorOutcome
from aptl.utils.probe_execution import probe_output_byte_limit


@dataclass(frozen=True)
class SourceResult:
    """One windowed source's typed result.

    ``status`` distinguishes a real capture / legitimate emptiness from each
    failure the source can detect (a returncode, a ``None`` HTTP result, a
    missing archive file). ``records`` are structured events the coordinator
    will serialize + redact; an over-limit source reports :attr:`dropped_count`
    rather than silently losing events.
    """

    status: CollectorStatus
    records: list[dict[str, object]] = field(default_factory=list)
    dropped_count: int = 0
    source_min_time: str | None = None
    source_max_time: str | None = None
    chunks: tuple[bytes, ...] = ()
    media_type: str = "application/json"
    observer_effect: str | None = None
    source_pipeline: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class WindowedSource(Protocol):
    """A narrow, source-owned windowed query returning a typed result."""

    def fetch(self, start_iso: str, end_iso: str) -> SourceResult:
        """Return the source's events in ``[start_iso, end_iso]`` as a typed result."""
        ...


_READ_BYTES: ContextVar[int | None] = ContextVar("capture_read_bytes", default=None)


def capture_read_bytes(requested: int) -> int:
    """Use the admitted artifact budget when bounding native reads."""
    return min(requested, _READ_BYTES.get() or requested)


def capture_read_timeout(requested: float) -> float:
    """Bound native reads through the backend's existing nested-call budget."""
    try:
        return cleanup_command_timeout(requested)
    except BackendTimeoutError:
        raise TimeoutExpired("capture-read", requested) from None


@dataclass(frozen=True)
class _WindowHandle:
    """Opaque per-start handle: the window's start time + the observation clock."""

    started_at: str
    clock: object
    deadline: float
    max_bytes: int


class CallableWindowedSource:
    """Adapt a plain ``fetch(start, end) -> SourceResult`` callable to a source.

    Lets a concrete built-in source be a thin function (or a bound method of a
    source owner) rather than a class, while keeping the narrow protocol.
    """

    def __init__(
        self,
        fetch: Callable[[str, str], SourceResult],
        *,
        readiness: Callable[[str], bool] | None = None,
    ) -> None:
        """Wrap a ``fetch(start_iso, end_iso) -> SourceResult`` callable."""
        self._fetch = fetch
        self._readiness = readiness

    def check_readiness(self, at_iso: str) -> bool:
        """Invoke only an explicitly supplied read-only owner operation."""
        return self._readiness is not None and self._readiness(at_iso) is True

    def fetch(self, start_iso: str, end_iso: str) -> SourceResult:
        """Delegate to the wrapped callable."""
        return self._fetch(start_iso, end_iso)


class WindowedQueryCollector:
    """The generic collector for a windowed source (media type ``application/json``).

    ``registration_id`` must match the pinned binding's; the coordinator
    verifies it. ``start`` records the window open from the injected clock and
    ``stop`` closes it, queries the source, and maps the typed result — a
    source failure becomes a distinct :class:`CollectorStatus`, never an empty
    success.
    """

    def __init__(self, registration_id: str, source: WindowedSource) -> None:
        """Bind this collector to its registration id and windowed source."""
        self._registration_id = registration_id
        self._source = source

    @property
    def registration_id(self) -> str:
        """The registration this collector realizes."""
        return self._registration_id

    def check_readiness(self, clock: ClockProvider) -> bool:
        """Require the source owner's separate bounded, read-only operation."""
        if probe_output_byte_limit() is None:
            return False
        operation = getattr(self._source, "check_readiness", None)
        return callable(operation) and operation(clock.now()) is True

    @staticmethod
    def start(context: CollectorContext) -> _WindowHandle:
        """Open the observation window from the injected clock."""
        return _WindowHandle(
            started_at=context.clock.now(),
            clock=context.clock,
            deadline=monotonic() + context.deadline_seconds,
            max_bytes=context.binding.limits.max_bytes,
        )

    def stop(self, handle: _WindowHandle) -> CollectorOutcome:
        """Close the window, query the source, and map its typed result."""
        window_end = handle.clock.now()
        byte_token = _READ_BYTES.set(handle.max_bytes)
        try:
            # Native I/O enforces the remaining budget at its boundary. Local,
            # already captured archives still need references after timeout.
            with native_read_budget(handle.deadline, monotonic):
                result = self._source.fetch(handle.started_at, window_end)
        except TimeoutExpired, BackendTimeoutError:
            result = SourceResult(status=CollectorStatus.TIMEOUT)
        except Exception:
            if monotonic() <= handle.deadline:
                raise
            result = SourceResult(status=CollectorStatus.TIMEOUT)
        finally:
            _READ_BYTES.reset(byte_token)
        finished_at = handle.clock.now()
        if monotonic() > handle.deadline:
            result = replace(result, status=CollectorStatus.TIMEOUT)
        return _to_outcome(result, handle.started_at, finished_at)


def source_result_to_outcome(
    result: SourceResult, started_at: str, finished_at: str
) -> CollectorOutcome:
    """Convert a source result through the existing collector outcome owner."""

    return _to_outcome(result, started_at, finished_at)


def _to_outcome(
    result: SourceResult, started_at: str, finished_at: str
) -> CollectorOutcome:
    """Map a :class:`SourceResult` to a :class:`CollectorOutcome`.

    Retain accepted content even when the source reports failure. Structured
    records serialize to ``application/json``; empty successful records are
    ``EMPTY_OK`` and failures keep their failure status.
    """
    has_content = bool(result.records or result.chunks)
    if result.status not in SUCCESS_STATUSES and not has_content:
        return CollectorOutcome(
            status=result.status,
            started_at=started_at,
            finished_at=finished_at,
            dropped_count=result.dropped_count,
            detail=f"source reported {result.status.value}",
        )
    status = result.status
    if status is CollectorStatus.OK and not has_content:
        status = CollectorStatus.EMPTY_OK
    chunks = (
        result.chunks
        if result.chunks
        else (json.dumps(result.records, separators=(",", ":")).encode("utf-8"),)
    )
    return CollectorOutcome(
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        chunks=chunks,
        media_type=result.media_type,
        event_count=len(result.records) if result.records else len(result.chunks),
        dropped_count=result.dropped_count,
        source_min_time=result.source_min_time,
        source_max_time=result.source_max_time,
        observer_effect=result.observer_effect,
        source_pipeline=result.source_pipeline,
    )
