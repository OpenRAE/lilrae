"""Resolve declared console endpoints and their necessary hostname mappings."""

from __future__ import annotations

import ipaddress
from collections.abc import Callable
from urllib.parse import SplitResult, urlsplit, urlunsplit

from aptl.core._port_bindings import _binding_host_ports
from aptl.core.deployment._compose_stateful_readiness import _published_host_port
from aptl.core.deployment._authored_service_hosts import node_service_origins

Inspect = Callable[[str], object]
ServedNames = Callable[[object, int], frozenset[str]]
_LOOPBACK = "127.0.0.1"


class ParticipantDesktopError(RuntimeError):
    """A desktop reference does not resolve to one realized, declared fact."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _console_url(
    node: object,
    service: str,
    inspect: Inspect,
    served_names: ServedNames,
) -> tuple[str, dict[str, str]]:
    """Return a console URL and the hostnames it needs, for one node service."""

    port = next(
        (
            int(item.port)
            for item in getattr(node, "services", ())
            if item.name == service
        ),
        None,
    )
    if port is None:
        raise ParticipantDesktopError("console-service-undeclared")
    scheme = _application_scheme(node, service)
    authored = node_service_origins(getattr(node, "runtime", None), service)
    if authored and scheme == "https":
        address = _node_address(node, inspect)
        return _canonical_console(authored, port, address)
    return _published_console(node, port, scheme, inspect, served_names)


def _published_console(
    node: object, port: int, scheme: str, inspect: Inspect, served_names: ServedNames
) -> tuple[str, dict[str, str]]:
    """Resolve one published port, then select its verified TLS identity."""

    info = inspect(str(node.container_name))
    bindings = info.get("NetworkSettings", {}).get("Ports", {}).get(f"{port}/tcp")
    candidates = _binding_host_ports(bindings)
    if len(candidates) > 1:
        raise ParticipantDesktopError("console-port-ambiguous")
    published = _published_host_port(info, port)
    if published is None:
        raise ParticipantDesktopError("console-port-unpublished")
    addresses = {
        binding.get("HostIp") for binding in bindings if isinstance(binding, dict)
    }
    if not addresses.intersection({_LOOPBACK, "0.0.0.0"}):
        raise ParticipantDesktopError("console-port-unreachable")
    if scheme != "https":
        return f"{scheme}://localhost:{published}/", {}
    return _tls_console(node, published, addresses, served_names)


def _tls_console(
    node: object, published: int, addresses: set[str], served_names: ServedNames
) -> tuple[str, dict[str, str]]:
    """Only verified names may influence browser URLs and host mappings."""

    try:
        names = served_names(node, published)
    except (OSError, ValueError):
        raise ParticipantDesktopError("console-certificate-untrusted") from None
    local = _covered_loopback(names)
    if local is not None:
        if local == "[::1]" and not addresses.intersection({"::", "::1"}):
            raise ParticipantDesktopError("console-port-unreachable")
        return f"https://{local}:{published}/", {}
    dns = sorted(name for name in names if not _is_address(name))
    if not dns:
        raise ParticipantDesktopError("console-certificate-unnamed")
    return f"https://{dns[0]}:{published}/", {dns[0]: _LOOPBACK}


def _canonical_console(
    origins: set[str], port: int, address: str
) -> tuple[str, dict[str, str]]:
    """Preserve the authored service URL without exposing URL credentials."""

    if len(origins) != 1:
        raise ParticipantDesktopError("console-origin-ambiguous")
    value = next(iter(origins))
    parsed = urlsplit(value)
    if _unsafe_origin(value, parsed):
        raise ParticipantDesktopError("console-origin-invalid")
    try:
        if parsed.port not in (None, port):
            raise ParticipantDesktopError("console-origin-port-unrealized")
    except ValueError:
        raise ParticipantDesktopError("console-origin-invalid") from None
    suffix = "" if port == 443 else f":{port}"
    return urlunsplit(
        ("https", f"{parsed.hostname}{suffix}", parsed.path or "/", "", "")
    ), {parsed.hostname: address}


def _unsafe_origin(value: str, parsed: SplitResult) -> bool:
    """Refuse URL credentials, controls and undisclosed query/fragment data."""

    return bool(
        any(ord(character) < 33 for character in value)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.hostname
    )


def _covered_loopback(names: frozenset[str]) -> str | None:
    """Return the URL host for a loopback identity the certificate covers.

    Only the exact covered identity is used: ``localhost`` when the certificate
    names it, otherwise its loopback IP address.
    """

    return next(
        (
            host
            for name, host in (
                ("localhost", "localhost"),
                (_LOOPBACK, _LOOPBACK),
                ("::1", "[::1]"),
            )
            if name in names
        ),
        None,
    )


def _application_scheme(node: object, service: str) -> str:
    """Return the protocol the node's SDL application declares for a service."""

    for application in (
        getattr(getattr(node, "runtime", None), "applications", None) or ()
    ):
        if str(getattr(application, "service", "")) == service:
            protocol = getattr(application, "protocol", "")
            value = str(getattr(protocol, "value", protocol)).lower()
            if value in {"http", "https"}:
                return value
    raise ParticipantDesktopError("console-protocol-undeclared")


def _node_address(node: object, inspect: Inspect) -> str:
    """Read the node's one realized network address from its owned container."""

    info = inspect(str(node.container_name))
    networks = (
        info.get("NetworkSettings", {}).get("Networks")
        if isinstance(info, dict)
        else None
    )
    addresses = {
        endpoint.get("IPAddress")
        for endpoint in (networks or {}).values()
        if isinstance(endpoint, dict) and endpoint.get("IPAddress")
    }
    if len(addresses) != 1:
        raise ParticipantDesktopError("node-address-ambiguous")
    address = addresses.pop()
    if not _is_address(address):
        raise ParticipantDesktopError("node-address-invalid")
    return address


def _is_address(value: str) -> bool:
    """Return whether ``value`` parses as an IP address."""

    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True
