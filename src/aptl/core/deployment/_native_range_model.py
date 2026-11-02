"""Reject native Compose paths that bypass the range bridge policy."""

from collections.abc import Callable, Mapping

_HOST_PATHS = {"/", "/run", "/var/run", "/proc", "/sys", "/dev"}
_HOST_CAPABILITIES = {"ALL", "SYS_ADMIN", "SYS_MODULE", "SYS_RAWIO"}


def validate_native_services(
    services: Mapping[str, object], resolve_owned_container: Callable[[str], str]
) -> None:
    """Require each namespace to terminate at an owned bridge workload."""
    for name, service in services.items():
        if not isinstance(service, dict):
            raise ValueError("native service must be a mapping")
        if service.get("privileged") or service.get("devices"):
            raise ValueError("native service exposes host devices")
        if _HOST_CAPABILITIES.intersection(service.get("cap_add", ())):
            raise ValueError("native service exposes host capabilities")
        _validate_namespace(name, services, resolve_owned_container)
        for mount in service.get("volumes", []):
            source = mount.get("source", "") if isinstance(mount, dict) else str(mount)
            if (
                "docker.sock" in source
                or source.rstrip("/") in _HOST_PATHS
                or source == "/"
            ):
                raise ValueError("native service exposes host authority")


def _validate_namespace(
    name: str,
    services: Mapping[str, object],
    resolve_owned_container: Callable[[str], str],
) -> None:
    seen: set[str] = set()
    while name not in seen:
        seen.add(name)
        service = services[name]
        mode = service.get("network_mode")
        if mode is None or mode == "none":
            return
        if mode.startswith("container:"):
            resolve_owned_container(mode.removeprefix("container:"))
            return
        if not mode.startswith("service:"):
            raise ValueError("native service bypasses bridge networking")
        name = mode.removeprefix("service:")
    raise ValueError("native service namespace cycle")
