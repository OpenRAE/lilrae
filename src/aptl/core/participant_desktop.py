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

import json
import os
import pwd
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import partial
from typing import Any
from pathlib import Path

from aptl.backends.participant_desktop import ParticipantDesktopSpec
from aptl.backends.raes_declared_credentials import (
    AccountCredentialReference,
    DeclaredCredentialError,
    resolve_declared_credential,
)
from aptl.core import _participant_desktop_files as files
from aptl.core._participant_desktop_tls import (
    served_certificate_names as verified_certificate_names,
)
from aptl.core._participant_desktop_endpoints import (
    Inspect,
    ServedNames,
    ParticipantDesktopError,
    _console_url,
    _node_address,
)
from aptl.core.deployment._authored_service_hosts import node_service_hosts
from aptl.core.participant_hosts import SCHEMA as HOSTS_SCHEMA
from aptl.core.participant_hosts import HostsPublicationError, validated_entries
from aptl.utils.pathsafe import (
    PathContainmentError,
    remove_contained_nofollow,
    replace_private_nofollow,
)

#: The participant account whose desktop receives the surface. Unset means the
#: lab has no participant desktop, and nothing is resolved or published.
ACCOUNT_VARIABLE = "LILRAE_PARTICIPANT_DESKTOP_ACCOUNT"
HOSTS_RELPATH = Path(".aptl") / "participant-desktop" / "hosts.json"
_MAX_GUIDE_BYTES = 1024 * 1024


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


def resolve_participant_desktop(
    spec: ParticipantDesktopSpec,
    *,
    read_asset: Callable[[str], bytes],
    accounts: Mapping[str, object],
    nodes: Sequence[object],
    inspect: Inspect,
    served_names: ServedNames,
) -> ResolvedDesktop:
    """Resolve every desktop reference, or refuse the whole surface."""

    observations: dict[str, dict[str, Any]] = {}

    def observed(container: str) -> dict[str, Any]:
        """Read back each owned container once and require a running instance."""

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
            hosts, dict.fromkeys(sorted(node_service_hosts(node.runtime)), address)
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
    except (OSError, ValueError, PathContainmentError):
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

    if not files.write_as_account(entry, request):
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
        except (OSError, ValueError, PathContainmentError):
            success = False
    try:
        remove_contained_nofollow(project_dir, HOSTS_RELPATH)
    except (OSError, ValueError, PathContainmentError):
        success = False
    if not account:
        return success
    try:
        _write_files(pwd.getpwnam(account), {}, run_as_account)
    except (
        KeyError,
        OSError,
        ValueError,
        PathContainmentError,
        ParticipantDesktopError,
    ):
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
    from aptl.backends.participant_desktop import (
        ParticipantDesktopProviderError,
    )

    try:
        return _start_surface(project_dir, admitted_start, backend, account)
    except (ParticipantDesktopError, ParticipantDesktopProviderError) as exc:
        failure = exc.code
    except (KeyError, OSError, ValueError, PathContainmentError) as exc:
        failure = type(exc).__name__
    withdraw_participant_desktop(project_dir, account)
    return failure


def _start_surface(
    project_dir: Path, admitted: object, backend: object, account: str
) -> str | None:
    """Select, resolve and publish one admitted desktop inside the failure boundary."""

    from aptl.backends.participant_desktop import select_participant_desktop
    from aptl.backends.scenario_startup import StartupCapability

    inspect = getattr(backend, "container_inspect", None)
    if not callable(inspect):
        raise ParticipantDesktopError("backend-unavailable")
    bundle, realization = admitted.bundle, admitted.realization
    startup = getattr(getattr(admitted, "startup_selection", None), "plan", None)
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
        accounts=dict(getattr(admitted.scenario, "accounts", {}) or {}),
        nodes=tuple(realization.nodes),
        inspect=inspect,
        served_names=partial(verified_certificate_names, bundle.root, realization),
    )
    publish_participant_desktop(project_dir, resolved, account)
    return None


__all__ = (
    "ACCOUNT_VARIABLE",
    "HOSTS_RELPATH",
    "ParticipantDesktopError",
    "ResolvedDesktop",
    "ResolvedLogin",
    "publish_participant_desktop",
    "resolve_participant_desktop",
    "start_participant_desktop",
    "withdraw_participant_desktop",
)
