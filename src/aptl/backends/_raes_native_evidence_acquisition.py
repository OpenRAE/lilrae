"""Immediate native-evidence request model and acquisition entry point."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import TYPE_CHECKING

from aptl.core.correlation.clock import ClockProvider, SystemClockProvider
from aptl.core.evidence.coordinator import AcquisitionResult, acquire_evidence
from aptl.core.evidence.adapters.sources import (
    SourceResult,
    WindowedSource,
    _to_outcome,
)
from aptl.core.evidence.content_store import create_run_json_once
from aptl.core.evidence.outcomes import AcquisitionPhase, CollectorStatus
from aptl.core.evidence.protocol import CollectorContext, CollectorOutcome, RunScope
from aptl.backends.scenario_capture import capture_run_scope
from aptl.core.experiment.capture_registry import CaptureBinding, CollectorRegistration
from aptl.core.runstore import LocalRunStore

if TYPE_CHECKING:
    from aptl.backends.scenario_capture import ResolvedScenarioCapture
    from aptl.backends.raes_realization_model import AptlRealization
    from aptl.core.experiment.capture_plan import CapturePlan


@dataclass(frozen=True)
class NativeEvidenceRequest:
    """All authority and runtime inputs for immediate native acquisition."""

    plan: CapturePlan
    backend: object
    realization: AptlRealization
    project_dir: Path
    environment: Mapping[str, str]
    run_store: LocalRunStore
    run_id: str
    capture_selection: ResolvedScenarioCapture
    clock: ClockProvider | None = None
    window: tuple[str, str] | None = None


@dataclass(frozen=True)
class _OnDemandHandle:
    """Collector context and the exact native-check start instant."""

    context: CollectorContext
    started_at: str


def _parse_timestamp(value: str) -> datetime:
    """Parse the canonical UTC timestamp form emitted by capture clocks."""

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _deadline(started_at: str, seconds: float) -> str:
    """Return the admitted deadline measured from a collector start."""

    value = _parse_timestamp(started_at) + timedelta(seconds=seconds)
    return value.isoformat().replace("+00:00", "Z")


def _source_times_inside_actual_window(
    result: SourceResult, started_at: str, finished_at: str
) -> bool:
    """Return whether all reported source instants fit the actual window."""

    try:
        start = _parse_timestamp(started_at)
        finish = _parse_timestamp(finished_at)
        source_min = (
            _parse_timestamp(result.source_min_time)
            if result.source_min_time is not None
            else None
        )
        source_max = (
            _parse_timestamp(result.source_max_time)
            if result.source_max_time is not None
            else None
        )
    except TypeError, ValueError:
        return False
    return (
        start <= finish
        and (source_min is None or start <= source_min <= finish)
        and (source_max is None or start <= source_max <= finish)
        and (source_min is None or source_max is None or source_min <= source_max)
    )


class _OnDemandNativeCollector:
    """Run one bounded native check and close its window after the check."""

    def __init__(self, registration_id: str, source: WindowedSource) -> None:
        self._registration_id = registration_id
        self._source = source

    @property
    def registration_id(self) -> str:
        return self._registration_id

    @staticmethod
    def start(context: CollectorContext) -> _OnDemandHandle:
        return _OnDemandHandle(context=context, started_at=context.clock.now())

    def stop(self, handle: _OnDemandHandle) -> CollectorOutcome:
        result = self._source.fetch(
            handle.started_at,
            _deadline(handle.started_at, handle.context.deadline_seconds),
        )
        finished_at = handle.context.clock.now()
        if not _source_times_inside_actual_window(
            result, handle.started_at, finished_at
        ):
            # Drop the time-correlated records, whose timing is untrustworthy,
            # but keep the probe residue so a skewed preparation still retains
            # its observer effect.
            result = SourceResult(
                status=CollectorStatus.CLOCK_SKEW,
                observer_effect=result.observer_effect,
                source_pipeline=result.source_pipeline,
            )
        return _to_outcome(result, handle.started_at, finished_at)


def _native_bindings(
    plan: CapturePlan,
    selection: ResolvedScenarioCapture,
) -> tuple[CaptureBinding, ...]:
    """Select immediate bindings declared by the admitted adapter."""

    return tuple(
        binding
        for binding in plan.runtime_bindings()
        if binding.registration_id in selection.contribution.native_registration_ids
    )


def _persist_capture_plan(
    plan: CapturePlan, run_store: LocalRunStore, run_id: str
) -> None:
    """Create the run and seal the admitted capture plan exactly once."""

    relative_path = f"evidence/capture-plans/{plan.plan_id}.json"
    run_store.create_run(run_id)
    create_run_json_once(
        run_store, run_id, relative_path, json.loads(plan.canonical_bytes)
    )


def acquire_native_evidence(request: NativeEvidenceRequest) -> AcquisitionResult:
    """Collect every immediate native binding or return a failed disposition."""

    if not isinstance(request.run_store, LocalRunStore):
        raise TypeError("native evidence requires a local run store")
    scope = capture_run_scope(
        request.capture_selection.context,
        request.run_id,
        request.plan.plan_id,
        "provisioning",
    )
    bindings = _native_bindings(request.plan, request.capture_selection)
    _persist_capture_plan(request.plan, request.run_store, request.run_id)
    sources: Mapping[str, WindowedSource] = {}
    if request.capture_selection.contribution.native_registration_ids:
        from aptl.backends.scenario_capture import family_capture_sources

        # The transcript window may seal the capture plan first. The retained
        # enrollment marker establishes each trial once, so preparation always
        # asks to establish; an established trial stays read-only.
        sources = family_capture_sources(
            request,
            establish_enrollment=True,
            phase=AcquisitionPhase.PREPARATION,
        )
    collectors = {
        binding.registration_id: _OnDemandNativeCollector(
            binding.registration_id,
            sources[binding.registration_id],  # type: ignore[arg-type]
        )
        for binding in bindings
        if binding.registration_id in sources
    }
    return acquire_evidence(
        bindings=bindings,
        collectors=collectors,
        run_store=request.run_store,
        scope=scope,
        clock=request.clock or SystemClockProvider(),
        phase=AcquisitionPhase.PREPARATION,
    )


def _validate_capture_window(window: tuple[str, str] | None) -> None:
    """Require an ordered trial window with explicit time zones."""
    if window is None:
        return
    if len(window) != 2:
        raise ValueError("trial capture window is invalid")
    start, finish = (_parse_timestamp(value) for value in window)
    if start.tzinfo is None or finish.tzinfo is None or finish < start:
        raise ValueError("trial capture window is invalid")


def _validate_trial_bindings(
    bindings: Sequence[CaptureBinding],
    registrations: Mapping[str, CollectorRegistration],
) -> None:
    """Refuse changed collector declarations before reading any source."""
    for binding in bindings:
        registration = registrations.get(binding.registration_id)
        if registration is None or (
            binding.effective_config_digest != registration.effective_config_digest()
            or binding.implementation_version != registration.implementation_version
        ):
            raise ValueError("trial capture registration changed after admission")


def _validate_trial_sources(
    sources: Mapping[str, WindowedSource],
    registrations: Mapping[str, CollectorRegistration],
    bindings: Sequence[CaptureBinding],
    scope: RunScope,
) -> None:
    """Check source interfaces, registration membership, and participant attempt identity."""
    from aptl.core.evidence.participant_capture import ParticipantCaptureArchive

    if any(
        not isinstance(source, WindowedSource) or not callable(source.fetch)
        for source in sources.values()
    ):
        raise ValueError("trial capture source interface is invalid")
    if not set(sources).issubset(registrations):
        raise ValueError("unknown collector registration id")
    selected = {binding.registration_id: binding for binding in bindings}
    for registration_id, source in sources.items():
        if isinstance(source, ParticipantCaptureArchive) and (
            source.grant.scope != scope
            or source.grant.binding != selected.get(registration_id)
        ):
            raise ValueError("participant capture source belongs to another trial")


def _add_native_sources(
    request: NativeEvidenceRequest, combined: dict[str, WindowedSource]
) -> None:
    """Preserve healthy participant sources if the native source factory fails."""
    from aptl.backends.scenario_capture import family_capture_sources

    if request.capture_selection.contribution.native_registration_ids:
        try:
            native = family_capture_sources(
                request, phase=AcquisitionPhase.MEASUREMENT
            )
        except RuntimeError:
            native = {}
        if set(native) & set(combined):
            raise ValueError("duplicate trial capture source")
        combined.update(native)


def _sources_in_window(
    sources: dict[str, WindowedSource], window: tuple[str, str] | None
) -> dict[str, WindowedSource]:
    """Apply the caller's actual trial window during a later capture phase."""
    from aptl.core.evidence.adapters.sources import CallableWindowedSource

    if window is None:
        return sources
    window_start, window_end = window
    return {
        key: CallableWindowedSource(
            lambda _start, _end, source=source: source.fetch(window_start, window_end)
        )
        for key, source in sources.items()
    }


def _validate_trial_request(request: NativeEvidenceRequest, attempt_id: str) -> None:
    """Validate trial acquisition authority before composing its scoped sources."""
    if not isinstance(request.run_store, LocalRunStore):
        raise TypeError("trial evidence requires a local run store")
    if not isinstance(attempt_id, str) or not attempt_id or len(attempt_id) > 128:
        raise ValueError("trial capture attempt is invalid")
    _validate_capture_window(request.window)


def acquire_trial_evidence(
    request: NativeEvidenceRequest,
    *,
    attempt_id: str,
    sources: Mapping[str, WindowedSource] | None = None,
    trial_body: Callable[[], None] | None = None,
) -> AcquisitionResult:
    """Collect an admitted trial through the existing coordinator and ledger.

    Family adapters supply native sources through their existing contribution.
    Cleanup follows finalization even when the trial body fails.
    """
    from aptl.core.evidence.adapters.wiring import build_collectors
    from aptl.core.evidence.adapters.sources import CallableWindowedSource

    _validate_trial_request(request, attempt_id)
    registry = request.capture_selection.registry
    registrations = {item.registration_id: item for item in registry.registrations}
    bindings = request.plan.runtime_bindings()
    _validate_trial_bindings(bindings, registrations)
    scope = capture_run_scope(
        request.capture_selection.context,
        request.run_id,
        request.plan.plan_id,
        attempt_id,
    )
    combined = dict(sources or {})
    _validate_trial_sources(combined, registrations, bindings, scope)
    _add_native_sources(request, combined)
    if trial_body is None:
        # Capture may follow execution: retain healthy peers when another source is missing.
        for binding in bindings:
            combined.setdefault(
                binding.registration_id,
                CallableWindowedSource(
                    lambda *_: SourceResult(status=CollectorStatus.SOURCE_UNAVAILABLE)
                ),
            )
    collectors = build_collectors(
        _sources_in_window(combined, request.window), registry
    )
    _persist_capture_plan(request.plan, request.run_store, request.run_id)
    return acquire_evidence(
        bindings=bindings,
        collectors=collectors,
        run_store=request.run_store,
        scope=scope,
        clock=request.clock or SystemClockProvider(),
        trial_body=trial_body or (lambda: None),
        phase=AcquisitionPhase.MEASUREMENT,
    )


__all__ = ("NativeEvidenceRequest", "acquire_native_evidence", "acquire_trial_evidence")
