"""Code-owned capture of native participant exports and the worker audit log."""

from collections.abc import Iterator, Mapping
from datetime import datetime
from pathlib import Path
import re

from raes_backend_protocols.capabilities import ObservationCaptureOffer

from aptl.core.evidence.adapters.sources import CallableWindowedSource, SourceResult
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.experiment.capture_registry import (
    CaptureLimits,
    CaptureVisibility,
    CollectorRegistration,
)

SESSION_REGISTRATION = "lilrae.collector.participant-sessions"
AUDIT_REGISTRATION = "lilrae.collector.host-audit"
_MAX_BYTES = 64 * 1024 * 1024
_AUDIT_TIME = re.compile(rb"msg=audit\((\d+)\.\d+:\d+\)")


def trial_capture_registrations(
    source_refs: frozenset[str],
) -> tuple[CollectorRegistration, ...]:
    """Offer only the two sources that the installed trial runner supplies."""
    return tuple(
        _registration(name, role, source_refs)
        for name, role in (
            (SESSION_REGISTRATION, "lilrae.participant-sessions"),
            (AUDIT_REGISTRATION, "lilrae.host-audit"),
        )
    )


def _registration(
    name: str, role: str, source_refs: frozenset[str]
) -> CollectorRegistration:
    """Describe one raw, run-scoped log source and its capture offer."""
    offer = ObservationCaptureOffer(
        offer_id=name,
        offer_version="1.0.0",
        output_contract="experiment-evidence-record-v1",
        field_selectors=("",),
        artifact_roles=frozenset({role}),
        media_types=frozenset({"application/json"}),
        capture_kind="log",
        source_classes=frozenset({"apparatus"}),
        source_refs=source_refs,
        scopes=frozenset({"run"}),
        scope_refs=source_refs,
        channel_kinds=frozenset({"backend-log"}),
        channel_refs=frozenset({role}),
        window_kinds=frozenset({"run", "apparatus"}),
        integrity_modes=frozenset({"checksum"}),
        sensitivity="plain",
        availability="available",
        fidelity="complete",
        disclosure="full",
        retention_policy_refs=frozenset({"run_lifetime"}),
        export_policy="not-required",
        redaction_policy=None,
    )
    return CollectorRegistration(
        registration_id=name,
        implementation_version="1.0.0",
        contract_version="experiment-capture-spec/v1",
        channel_kind="backend-log",
        capture_kind="log",
        capture_scope="run",
        window_kinds=offer.window_kinds,
        media_types=offer.media_types,
        required_artifact_roles=offer.artifact_roles,
        supported_sensitivities=frozenset({"plain"}),
        supports_redaction=False,
        integrity_modes=offer.integrity_modes,
        sealing_modes=frozenset({"digest"}),
        supports_retention=True,
        supports_loss_disclosure=True,
        visibility_class=CaptureVisibility.EVALUATOR_ONLY,
        limits=CaptureLimits(_MAX_BYTES, 2 if name == SESSION_REGISTRATION else 1, 900),
        redaction_policies=frozenset(),
        retention_policies=offer.retention_policy_refs,
        capture_offer=offer,
    )


def participant_session_source(
    sessions: Mapping[str, Mapping[str, object]], participants: tuple[str, ...]
) -> CallableWindowedSource:
    """Retain every expected native export, including original per-call usage."""

    def fetch(_start: str, _end: str) -> SourceResult:
        """Report every native export, and a loss when one participant has none."""
        complete = bool(participants) and set(sessions) == set(participants)
        return SourceResult(
            status=CollectorStatus.OK if complete else CollectorStatus.MID_RUN_LOSS,
            records=[
                {"participant": key, "native_export": dict(value)}
                for key, value in sorted(sessions.items())
            ],
        )

    return CallableWindowedSource(fetch)


def host_audit_source(log_dir: Path = Path("/var/log/audit")) -> CallableWindowedSource:
    """Read only the audit service's fixed log directory, within the trial window."""

    def fetch(start: str, end: str) -> SourceResult:
        """Return the audit lines whose event time falls inside the trial window."""
        files = sorted(log_dir.glob("audit.log*"), key=_rotation_order)
        if not files:
            return SourceResult(status=CollectorStatus.SOURCE_UNAVAILABLE)
        return _read_audit_window(files, (_epoch_seconds(start), _epoch_seconds(end)))

    return CallableWindowedSource(fetch)


def _read_audit_window(files: list[Path], window: tuple[int, int]) -> SourceResult:
    """Collect the in-window lines of each rotated file, within the size limit."""
    lines: list[str] = []
    size = 0
    for path in files:
        if path.is_symlink() or not path.is_file():
            return SourceResult(status=CollectorStatus.MID_RUN_LOSS)
        for line in _window_lines(path, window):
            size += len(line)
            if size > _MAX_BYTES:
                return SourceResult(status=CollectorStatus.TRUNCATION, dropped_count=1)
            lines.append(line.decode("utf-8", errors="strict"))
    return SourceResult(
        status=CollectorStatus.OK if lines else CollectorStatus.EMPTY_OK,
        records=[{"audit_log": "".join(lines)}] if lines else [],
    )


def _window_lines(path: Path, window: tuple[int, int]) -> Iterator[bytes]:
    """Yield the lines of one audit file whose event second is inside the window."""
    first, last = window
    with path.open("rb") as source:
        for line in source:
            match = _AUDIT_TIME.search(line)
            if match is not None and first <= int(match[1]) <= last:
                yield line


def _epoch_seconds(value: str) -> int:
    """Convert one RFC 3339 time to whole seconds since the epoch."""
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def _rotation_order(path: Path) -> int:
    """Sort rotated audit files from the oldest to the current log."""
    suffix = path.name.removeprefix("audit.log").lstrip(".")
    return -int(suffix) if suffix.isdecimal() else 0
