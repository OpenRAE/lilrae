"""Keep the data a trial leaves behind in its run before the seal.

Two captures run after every participant ended:

* The scenario runtime adapter may dump its own product state (for example the
  SOC stack) through ``trial_end_capture``. Core keeps the returned files under
  ``trial/soc/`` and removes exact granted credentials first.
* The host audit log, when the worker host runs auditd, is kept for the trial
  window under ``trial/audit/audit.log``.

Each capture writes a status file, so a missing source is visible and never
silently absent. A capture failure never prevents the seal.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from aptl.core.runstore import LocalRunStore
from aptl.utils.logging import get_logger
from aptl.utils.redaction import redact_granted_secrets

log = get_logger("trial_end_capture")

AUDIT_LOG_DIR = Path("/var/log/audit")
#: Bound for the kept audit records; the status file records a truncation.
MAX_AUDIT_BYTES = 1024 * 1024 * 1024
_FILE_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_SECRET_KEY = re.compile(r"(PASSWORD|SECRET|TOKEN|API_KEY|_KEY)$")
_AUDIT_TIME = re.compile(rb"msg=audit\((\d+)\.\d+:\d+\)")


def retain_soc_dump(
    store: LocalRunStore,
    run_id: str,
    *,
    adapter: object | None,
    backend: object | None,
    node_names: tuple[str, ...],
    environment: Mapping[str, str],
) -> None:
    """Keep the adapter's trial-end product dump, or record why it is absent."""

    from aptl.backends.scenario_capture import TrialEndCaptureContext
    from aptl.backends.scenario_runtime_hooks import AdmittedRuntimeOperations

    capture = getattr(adapter, "trial_end_capture", None)
    status: dict[str, object]
    if not callable(capture) or backend is None:
        status = {"status": "unavailable", "reason": "no trial-end capture or backend"}
    else:
        nodes = [SimpleNamespace(name=_container_name(name)) for name in node_names]
        try:
            files = capture(
                TrialEndCaptureContext(AdmittedRuntimeOperations(backend, nodes))
            )
            secrets = tuple(
                value
                for key, value in environment.items()
                if _SECRET_KEY.search(key) and len(value) >= 8
            )
            for name, data in dict(files).items():
                if (
                    not isinstance(name, str)
                    or not _FILE_NAME.fullmatch(name)
                    or not isinstance(data, bytes)
                ):
                    raise ValueError("invalid trial-end capture file")
                text = data.decode("utf-8", errors="replace")
                store.write_file(
                    run_id,
                    f"trial/soc/{name}",
                    str(redact_granted_secrets(text, secrets)).encode(),
                )
            status = {"status": "captured", "files": sorted(files)}
        except Exception as exc:
            # Adapter errors can carry product output; keep the type only.
            log.warning("trial-end product capture failed: %s", type(exc).__name__)
            status = {"status": "failed", "reason": type(exc).__name__}
    store.write_file(
        run_id, "trial/soc/status.json", json.dumps(status, sort_keys=True).encode()
    )


def retain_host_audit(
    store: LocalRunStore,
    run_id: str,
    *,
    started_at: str,
    ended_at: str,
    log_dir: Path = AUDIT_LOG_DIR,
) -> None:
    """Keep the host audit records of the ISO 8601 trial window, or record why they are absent."""

    files = (
        sorted(log_dir.glob("audit.log*"), key=_rotation_order)
        if log_dir.is_dir()
        else []
    )
    status: dict[str, object] = {
        "status": "unavailable",
        "reason": "host audit log is absent",
    }
    if files:
        start = int(_instant(started_at).timestamp())
        end = int(_instant(ended_at).timestamp()) + 1
        try:
            kept, size, truncated = _audit_window(files, start, end)
            store.write_file(run_id, "trial/audit/audit.log", b"".join(kept))
            status = {
                "status": "captured",
                "records": len(kept),
                "bytes": size,
                "truncated": truncated,
            }
        except OSError as exc:
            log.warning("host audit capture failed: %s", type(exc).__name__)
            status = {"status": "failed", "reason": type(exc).__name__}
    store.write_file(
        run_id, "trial/audit/status.json", json.dumps(status, sort_keys=True).encode()
    )


def _audit_window(
    files: list[Path], start: int, end: int
) -> tuple[list[bytes], int, bool]:
    """Return the window's records oldest first; stop at the first one over the bound.

    The kept records stay contiguous, so a truncated log has no gap.
    """
    kept: list[bytes] = []
    size = 0
    for line in _window_lines(files, start, end):
        if size + len(line) > MAX_AUDIT_BYTES:
            return kept, size, True
        kept.append(line)
        size += len(line)
    return kept, size, False


def _window_lines(files: list[Path], start: int, end: int) -> Iterator[bytes]:
    """Yield each audit record whose time is in ``[start, end]``, in file order."""
    for path in files:
        for line in path.read_bytes().splitlines(keepends=True):
            match = _AUDIT_TIME.search(line)
            if match is not None and start <= int(match.group(1)) <= end:
                yield line


def _instant(value: str) -> datetime:
    """Parse one ISO 8601 UTC time, accepting a ``Z`` suffix."""

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _rotation_order(path: Path) -> int:
    """Order ``audit.log.N`` oldest first and ``audit.log`` last."""

    suffix = path.name.removeprefix("audit.log").lstrip(".")
    return -int(suffix) if suffix.isdecimal() else 0


def _container_name(name: str) -> str:
    """Return the deployment container name of one SDL node."""

    return name if name.startswith("aptl-") else f"aptl-{name}"


__all__ = ["retain_host_audit", "retain_soc_dump"]
