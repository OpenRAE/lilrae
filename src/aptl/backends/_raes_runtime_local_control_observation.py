"""Provider-observed disclosure of the runtime local control interfaces.

Daemon mount metadata corroborates the admitted Docker socket bind. A recorded
socket source replaces the canonical source when the backend records Docker use.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from raes.runtime_configuration import RuntimeConfiguration

from aptl.backends._runtime_concern_disclosure import _disclose

_DOCKER_SOCKET = "/var/run/docker.sock"


def recorded_socket_source(backend: object, container_name: str) -> str | None:
    """Return the recorded Docker socket source for one container, if known."""
    reader = getattr(backend, "recorded_docker_source", None)
    source = reader(container_name) if callable(reader) else None
    return source if isinstance(source, str) else None


def observe_local_control_interfaces(
    info: Mapping[str, Any],
    runtime: RuntimeConfiguration,
    *,
    recording_source: str | None = None,
) -> object | None:
    """Corroborate the canonical Docker socket from daemon mount metadata."""

    interfaces = tuple(runtime.local_control_interfaces)
    mounts = info.get("Mounts")
    corroborated = bool(
        interfaces
        and isinstance(mounts, list)
        and all(
            _local_control_interface_matches(item, mounts, recording_source)
            for item in interfaces
        )
    )
    value = [item.model_dump(mode="json", by_alias=True) for item in interfaces]
    return (
        _disclose("runtime-local-control-interfaces", value) if corroborated else None
    )


def _local_control_interface_matches(
    interface: object, mounts: list[object], recording_source: str | None = None
) -> bool:
    """Corroborate the canonical Docker socket in daemon mount metadata."""

    expected = _supported_local_control_interface(interface)
    return expected is not None and any(
        _local_control_mount_matches(
            mount, recording_source or expected[0], expected[1]
        )
        for mount in mounts
    )


def _supported_local_control_interface(interface: object) -> tuple[str, str] | None:
    """Return the admitted Docker socket source and access mode."""

    kind = str(getattr(interface.kind, "value", interface.kind))
    access = str(getattr(interface.access, "value", interface.access))
    source = interface.bind_source or interface.path
    supported = (
        kind == "unix_socket"
        and access in {"read_only", "read_write"}
        and interface.path == _DOCKER_SOCKET
        and source == _DOCKER_SOCKET
        and not interface.protocol
    )
    return (source, access) if supported else None


def _local_control_mount_matches(mount: object, source: str, access: str) -> bool:
    """Compare one daemon-observed bind mount to the admitted interface."""

    return bool(
        isinstance(mount, Mapping)
        and mount.get("Type") == "bind"
        and mount.get("Source") == source
        and mount.get("Destination") == _DOCKER_SOCKET
        and bool(mount.get("RW")) == (access == "read_write")
    )
