"""Pure adapter support functions for TechVault native evidence."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from typing import IO

from aptl.core.evidence.spool import iter_spool, new_spool

UTC_OFFSET = "+00:00"


def utc_iso_now() -> str:
    """Return the current UTC instant in canonical ISO form."""

    return datetime.now(timezone.utc).isoformat().replace(UTC_OFFSET, "Z")


def stream_container_file(
    operations: object, container: str, path: str
) -> tuple[IO[bytes] | None, str | None]:
    """Stream one complete container file into a spool; return it or a loss code.

    The caller closes the returned spool.
    """
    stream = getattr(operations, "container_exec_stream", None)
    spool = new_spool()
    loss = "source-exec-failed" if not callable(stream) else None
    if loss is None:
        with new_spool() as stderr:
            try:
                ended = stream(
                    container, ["cat", "--", path], stdout=spool, stderr=stderr
                )
            # broad-except: backend transports expose implementation-specific failures.
            except Exception:
                ended = None
        loss = _stream_loss(ended)
    if loss is not None:
        spool.close()
        return None, loss
    return spool, None


def _stream_loss(ended: object | None) -> str | None:
    """Return the loss code of a streamed read, or ``None`` when it succeeded."""
    checks = (
        (ended is None, "source-exec-failed"),
        (getattr(ended, "timed_out", False), "source-read-timed-out"),
        (getattr(ended, "failed_pipe", False), "source-read-interrupted"),
        (getattr(ended, "returncode", 0) != 0, "source-command-failed"),
    )
    return next((loss for failed, loss in checks if failed), None)


def spool_lines(spool: IO[bytes]) -> Iterator[tuple[bytes, bool]]:
    """Yield each line of ``spool`` and whether it ended with a newline."""
    pending = b""
    for chunk in iter_spool(spool):
        pending += chunk
        *complete, pending = pending.split(b"\n")
        for line in complete:
            yield line, True
    if pending:
        yield pending, False


def find_node(realization: object, name: str) -> object | None:
    """Find one named node in a deployment realization."""

    return next(
        (
            item
            for item in getattr(realization, "nodes", ())
            if getattr(item, "name", None) == name
        ),
        None,
    )


def content_identities(realization: object) -> dict[str, str] | None:
    """Project the two exact admitted Suricata content identities."""

    required = {"suricata-config", "suricata-local-rules"}
    identities: dict[str, str] = {}
    valid = True
    for placement in getattr(realization, "placements", ()):
        content = getattr(placement, "content", None)
        name = getattr(content, "content_name", None)
        if name not in required:
            continue
        artifact_id = getattr(content, "artifact_id", None)
        digest = getattr(content, "artifact_digest", None)
        if not isinstance(artifact_id, str) or not isinstance(digest, str):
            valid = False
            break
        identities[name] = f"{artifact_id}@{digest}"
    return identities if valid and set(identities) == required else None


def webapp_endpoint(realization: object) -> tuple[str, int] | None:
    """Resolve the unique static Kali-to-webapp HTTP endpoint."""

    kali = find_node(realization, "kali")
    webapp = find_node(realization, "webapp")
    result: tuple[str, int] | None = None
    if kali is not None and webapp is not None:
        kali_networks = dict(getattr(kali, "static_address_assignments", ()))
        web_networks = dict(getattr(webapp, "static_address_assignments", ()))
        shared = sorted(set(kali_networks) & set(web_networks))
        http = [
            item
            for item in getattr(webapp, "services", ())
            if getattr(item, "name", None) == "http"
            and getattr(item, "protocol", "tcp") == "tcp"
        ]
        if shared and len(http) == 1:
            port = getattr(http[0], "port", None)
            if isinstance(port, int) and 0 < port <= 65535:
                # Multiple authored paths may connect Kali and the application.
                # Choose one deterministically; the traffic apparatus uses the
                # same rule, so collection and observation stay on one path.
                result = (web_networks[shared[0]], port)
    return result


def webapp_address(realization: object) -> str | None:
    """Resolve the unique static Kali-to-webapp address."""

    endpoint = webapp_endpoint(realization)
    return endpoint[0] if endpoint is not None else None


def inside_window(value: object, start_iso: str, end_iso: str) -> bool:
    """Return whether an ISO timestamp falls inside the closed evidence window."""

    try:
        instant = datetime.fromisoformat(str(value).replace("Z", UTC_OFFSET))
        start = datetime.fromisoformat(start_iso.replace("Z", UTC_OFFSET))
        end = datetime.fromisoformat(end_iso.replace("Z", UTC_OFFSET))
    except (TypeError, ValueError):
        return False
    return start <= instant <= end


__all__ = (
    "content_identities",
    "find_node",
    "inside_window",
    "spool_lines",
    "stream_container_file",
    "utc_iso_now",
    "webapp_address",
    "webapp_endpoint",
)
