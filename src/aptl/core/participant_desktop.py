"""Resolve and publish the participant desktop surface (issue #1273).

A pack-bound provider names what the desktop shows as references
(:mod:`aptl.backends.participant_desktop`). This module resolves each one
against the admitted SDL and the realized lab, then publishes the result:

* a console URL is the node's authored ``https`` canonical URL when the SDL
  authors one; otherwise it is the service's realized published loopback port,
  under the name the certificate it actually serves covers;
* a hostname maps to the node's realized address, read back from its owned
  container; a certificate name maps to loopback, where the port is published;
* a login is the account's authored ``secret_fixture`` and nothing else;
* the guide is the bundle asset the provider names.

Only the non-secret hostname list persists in lab state
(``.aptl/participant-desktop/hosts.json``), for
:mod:`aptl.core.participant_hosts` to apply. The logins, guide, and console list
go straight into the participant account's private desktop directory.
"""

from __future__ import annotations

import ipaddress
import json
import os
import pwd
import socket
import ssl
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from aptl.backends.participant_desktop import ParticipantDesktopSpec
from aptl.backends.raes_declared_credentials import (
    AccountCredentialReference,
    DeclaredCredentialError,
    resolve_declared_credential,
)
from aptl.core import _participant_desktop_files as files
from aptl.core.deployment._authored_service_hosts import (
    node_service_hosts,
    node_service_origins,
)
from aptl.core._port_bindings import _binding_host_ports
from aptl.core.deployment._compose_stateful_readiness import _published_host_port
from aptl.core.participant_hosts import SCHEMA as HOSTS_SCHEMA
from aptl.core.participant_hosts import HostsPublicationError, validated_entries
from aptl.utils.pathsafe import remove_contained_nofollow, replace_private_nofollow

#: The participant account whose desktop receives the surface. Unset means the
#: lab has no participant desktop, and nothing is resolved or published.
ACCOUNT_VARIABLE = "LILRAE_PARTICIPANT_DESKTOP_ACCOUNT"
HOSTS_RELPATH = Path(".aptl") / "participant-desktop" / "hosts.json"
_LOOPBACK = "127.0.0.1"
_MAX_GUIDE_BYTES = 1024 * 1024
_TLS_TIMEOUT = 10

Inspect = Callable[[str], object]
ServedNames = Callable[[int], frozenset[str]]


class ParticipantDesktopError(RuntimeError):
    """A desktop reference does not resolve to one realized, declared fact."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ResolvedLogin:
    """One declared console login."""

    label: str
    username: str
    secret: str = field(repr=False)


@dataclass(frozen=True)
class ResolvedDesktop:
    """The desktop surface after every reference resolved."""

    consoles: tuple[tuple[str, str], ...]
    logins: tuple[ResolvedLogin, ...]
    guide: bytes | None
    hosts: tuple[tuple[str, str], ...]


def served_certificate_names(port: int) -> frozenset[str]:
    """Return the DNS and IP names of the certificate served on a loopback port.

    This reads what the console presents, without verifying it: the name it
    returns is only used to choose the URL the participant's browser opens,
    and that browser verifies the certificate against the lab trust anchors.
    """

    from cryptography import x509

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((_LOOPBACK, port), timeout=_TLS_TIMEOUT) as raw:
        with context.wrap_socket(raw) as tls:
            der = tls.getpeercert(binary_form=True)
    if not der:
        return frozenset()
    certificate = x509.load_der_x509_certificate(der)
    try:
        names = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
    except x509.ExtensionNotFound:
        return frozenset()
    dns = names.get_values_for_type(x509.DNSName)
    addresses = [str(value) for value in names.get_values_for_type(x509.IPAddress)]
    return frozenset(name.lower() for name in (*dns, *addresses))


def resolve_participant_desktop(
    spec: ParticipantDesktopSpec,
    *,
    read_asset: Callable[[str], bytes],
    accounts: Mapping[str, object],
    nodes: Sequence[object],
    inspect: Inspect,
    served_names: ServedNames = served_certificate_names,
) -> ResolvedDesktop:
    """Resolve every desktop reference, or refuse the whole surface."""

    observations = {}

    def observed(container: str):
        if container not in observations:
            info = inspect(container)
            if (
                not isinstance(info, dict)
                or info.get("State", {}).get("Running") is not True
            ):
                raise ParticipantDesktopError("node-not-ready")
            observations[container] = info
        return observations[container]

    by_name = {str(getattr(node, "name", "")): node for node in nodes}
    hosts: dict[str, str] = {}
    consoles = []
    for console in spec.consoles:
        node = _node(by_name, console.node)
        url, mapped = _console_url(node, console.service, observed, served_names)
        consoles.append((console.label, url))
        _merge_hosts(hosts, mapped)
    for name in spec.hostnames:
        node = _node(by_name, name)
        address = _node_address(node, observed)
        _merge_hosts(
            hosts, {host: address for host in sorted(node_service_hosts(node.runtime))}
        )
    logins = tuple(_login(accounts, item) for item in spec.credentials)
    guide = _guide(read_asset, spec.guide)
    pairs = tuple(sorted((address, host) for host, address in hosts.items()))
    try:
        validated_entries(_hosts_document(pairs))
    except HostsPublicationError:
        raise ParticipantDesktopError("hostname-invalid") from None
    return ResolvedDesktop(tuple(consoles), logins, guide, pairs)


def _merge_hosts(hosts: dict[str, str], mapped: Mapping[str, str]) -> None:
    """Add hostname bindings; refuse a name already bound to another address."""

    for host, address in mapped.items():
        if hosts.setdefault(host, address) != address:
            raise ParticipantDesktopError("hostname-conflict")


def _node(by_name: Mapping[str, object], name: str) -> object:
    """Return the realized node an SDL name names, or refuse."""

    node = by_name.get(name)
    if node is None or not getattr(node, "container_name", None):
        raise ParticipantDesktopError("node-unrealized")
    return node


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
    names = served_names(published)
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
    if (
        any(ord(character) < 33 for character in value)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.hostname
    ):
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


def _covered_loopback(names: frozenset[str]) -> str | None:
    """Return the URL host for a loopback identity the certificate covers.

    Only the exact covered identity is used: ``localhost`` when the certificate
    names it, otherwise its loopback IP address.
    """

    if "localhost" in names:
        return "localhost"
    if _LOOPBACK in names:
        return _LOOPBACK
    if "::1" in names:
        return "[::1]"
    return None


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


def _login(accounts: Mapping[str, object], item: object) -> ResolvedLogin:
    """Return one declared login, from its authored ``secret_fixture`` only."""

    try:
        credential = resolve_declared_credential(
            accounts, AccountCredentialReference(item.account, item.credential_id)
        )
    except DeclaredCredentialError as exc:
        raise ParticipantDesktopError(f"login-{exc.code}") from None
    return ResolvedLogin(item.label, credential.username, credential.value)


def _guide(read_asset: Callable[[str], bytes], path: str | None) -> bytes | None:
    """Read the bounded guide asset the provider names."""

    if path is None:
        return None
    try:
        data = read_asset(path)
    except (OSError, ValueError):
        raise ParticipantDesktopError("guide-unavailable") from None
    if len(data) > _MAX_GUIDE_BYTES:
        raise ParticipantDesktopError("guide-too-large")
    return data


def _hosts_document(pairs: Sequence[tuple[str, str]]) -> dict[str, object]:
    """Return the ``hosts.json`` document for ``pairs``."""

    return {
        "schema": HOSTS_SCHEMA,
        "entries": [{"address": address, "hostname": host} for address, host in pairs],
    }


def publish_participant_desktop(
    project_dir: Path,
    desktop: ResolvedDesktop,
    account: str,
    *,
    run_as_account: Callable[[pwd.struct_passwd, str], None] | None = None,
) -> None:
    """Persist the hostnames and write the participant's private desktop files."""

    replace_private_nofollow(
        project_dir,
        HOSTS_RELPATH,
        (json.dumps(_hosts_document(desktop.hosts), indent=2) + "\n").encode("utf-8"),
    )
    entry = pwd.getpwnam(account)
    payload = {
        files.CREDENTIALS_FILE: files.render_credentials(
            [(login.label, login.username, login.secret) for login in desktop.logins]
        ),
        files.CONSOLES_FILE: files.render_consoles(
            [url for _label, url in desktop.consoles]
        ),
    }
    if desktop.guide is not None:
        payload[files.GUIDE_FILE] = files.render_guide(desktop.guide)
    _write_files(entry, payload, run_as_account)


def _write_files(
    entry: pwd.struct_passwd,
    payload: Mapping[str, bytes],
    run_as_account: Callable[[pwd.struct_passwd, str], None] | None,
) -> None:
    """Make ``payload`` the account's complete desktop surface."""

    home = Path(entry.pw_dir)
    if _effective_uid() == entry.pw_uid:
        files.write_desktop_files(home, payload)
        return
    if _effective_uid() != 0:
        raise ParticipantDesktopError("desktop-account-not-writable")
    (run_as_account or _write_as_account)(entry, files.encoded_request(home, payload))


def _effective_uid() -> int:
    """Return the effective user id this lab start runs as."""

    return os.geteuid()


def _write_as_account(entry: pwd.struct_passwd, request: str) -> None:
    """Run the desktop file writer as the participant, files on stdin."""

    environment = {"PYTHONPATH": os.pathsep.join(path for path in sys.path if path)}
    completed = subprocess.run(
        [sys.executable, "-m", "aptl.core._participant_desktop_files"],
        input=request,
        text=True,
        user=entry.pw_uid,
        group=entry.pw_gid,
        extra_groups=[],
        env=environment,
        cwd=entry.pw_dir,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise ParticipantDesktopError("desktop-files-not-written")


def withdraw_participant_desktop(
    project_dir: Path,
    account: str | None = None,
    *,
    run_as_account: Callable[[pwd.struct_passwd, str], None] | None = None,
) -> bool:
    """Remove the hostname list and the account's desktop files.

    A start whose desktop failed, or whose pack has no desktop, must leave no
    earlier run's hostnames, logins, guide or consoles behind. Withdrawal is
    best effort: a failure to remove leaves the start's own failure standing.
    """

    if account is None:
        account = os.environ.get(ACCOUNT_VARIABLE, "").strip()
    success = True
    if _effective_uid() == 0 and os.environ.get("APTL_SEAT_DESKTOP_HANDOFF") == "1":
        from aptl.core.participant_hosts import clear

        try:
            clear()
        except (OSError, ValueError):
            success = False
    try:
        remove_contained_nofollow(project_dir, HOSTS_RELPATH)
    except (OSError, ValueError):
        success = False
    if not account:
        return success
    try:
        _write_files(pwd.getpwnam(account), {}, run_as_account)
    except (KeyError, OSError, ValueError, ParticipantDesktopError):
        return False
    return success


def start_participant_desktop(
    project_dir: Path,
    admitted_start: object,
    backend: object,
) -> str | None:
    """Resolve and publish the admitted pack's desktop for one lab start.

    Returns ``None`` when the lab has no participant desktop account, the pack
    has no desktop provider, or publication succeeded. Otherwise it withdraws
    any earlier hostname list and returns a stable failure code, so the
    desktop never shows a previous run's surface.
    """

    account = os.environ.get(ACCOUNT_VARIABLE, "").strip()
    bundle = getattr(admitted_start, "bundle", None)
    realization = getattr(admitted_start, "realization", None)
    if not account or bundle is None or realization is None:
        return None
    inspect = getattr(backend, "container_inspect", None)
    if not callable(inspect):
        withdraw_participant_desktop(project_dir, account)
        return "backend-unavailable"
    from aptl.backends.participant_desktop import (
        ParticipantDesktopProviderError,
        select_participant_desktop,
    )

    try:
        from aptl.backends.scenario_startup import StartupCapability

        startup = getattr(
            getattr(admitted_start, "startup_selection", None), "plan", None
        )
        required = StartupCapability.PARTICIPANT_DESKTOP in getattr(
            startup, "lifecycle_capabilities", ()
        )
        spec = select_participant_desktop(bundle, required=required)
        if spec is None:
            return (
                None
                if withdraw_participant_desktop(project_dir, account)
                else "desktop-withdrawal-failed"
            )
        resolved = resolve_participant_desktop(
            spec,
            read_asset=bundle.read_asset,
            accounts=dict(getattr(admitted_start.scenario, "accounts", {}) or {}),
            nodes=tuple(realization.nodes),
            inspect=inspect,
        )
        publish_participant_desktop(project_dir, resolved, account)
    except (ParticipantDesktopError, ParticipantDesktopProviderError) as exc:
        withdraw_participant_desktop(project_dir, account)
        return exc.code
    except (KeyError, OSError, ValueError, ssl.SSLError) as exc:
        withdraw_participant_desktop(project_dir, account)
        return type(exc).__name__
    return None


__all__ = (
    "ACCOUNT_VARIABLE",
    "HOSTS_RELPATH",
    "ParticipantDesktopError",
    "ResolvedDesktop",
    "ResolvedLogin",
    "publish_participant_desktop",
    "resolve_participant_desktop",
    "served_certificate_names",
    "start_participant_desktop",
    "withdraw_participant_desktop",
)
