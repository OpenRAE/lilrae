"""Initial native readback of directory, file and DNS service configuration."""

from __future__ import annotations

import configparser
import io
import shlex
from typing import TYPE_CHECKING

from raes.runtime_configuration import RuntimeConfiguration

from aptl.backends._raes_observation_helpers import observed_domain_topology
from aptl.backends._runtime_concern_disclosure import _disclose

if TYPE_CHECKING:
    from aptl.core.deployment.backend import DeploymentBackend


def native_text(
    backend: DeploymentBackend, container: str, argv: list[str]
) -> str | None:
    """Read native command output without retaining it in diagnostics."""
    result = backend.container_exec(container, argv, timeout=30)
    return result.stdout if result.returncode == 0 else None


def observe_identity_authorities(
    backend: DeploymentBackend, container: str, runtime: RuntimeConfiguration
) -> object | None:
    """Confirm the served Samba domain and the directory's listening services."""
    records = runtime.identity_authorities
    if not records:
        return None
    sockets = backend.observe_container_listeners(container)
    for record in records:
        if record.kind != "domain" or any(
            (
                record.subjects,
                record.policies,
                record.relationships,
                record.resource_scopes,
                record.identity_uses,
                record.access_observations,
            )
        ):
            return None
        expected = {
            "dns_name": record.domain_name.lower(),
            "netbios_name": record.domain_name.split(".")[0].upper(),
            "role": "controller",
        }
        if observed_domain_topology(backend, container, expected) is None:
            return None
        if record.realm and record.realm != record.domain_name.upper():
            return None
        naming_context = ",".join(
            "DC=" + part for part in record.domain_name.split(".")
        )
        if record.base_dn and record.base_dn.casefold() != naming_context.casefold():
            return None
        for service in record.services:
            if service.protocol not in {"ldap", "ldaps", "kerberos", "ad_ds_rpc"}:
                return None
            if sockets is None or not any(
                protocol == "tcp" and port == service.port
                for protocol, _host, port in sockets.sockets
            ):
                return None
    return _disclose(
        "runtime-identity-authorities", [r.model_dump(mode="json") for r in records]
    )


def observe_file_services(
    backend: DeploymentBackend, container: str, runtime: RuntimeConfiguration
) -> object | None:
    """Read Samba's effective shares and local principal presence."""
    records = runtime.file_services
    if not records:
        return None
    text = native_text(backend, container, ["testparm", "-s", "--suppress-prompt"])
    if text is None:
        return None
    config = configparser.RawConfigParser(strict=False)
    try:
        config.read_file(io.StringIO(text))
        matched = all(
            _file_service_matches(backend, container, config, r) for r in records
        )
    except configparser.Error, ValueError:
        return None
    return (
        _disclose("runtime-file-services", [r.model_dump(mode="json") for r in records])
        if matched
        else None
    )


def _file_service_matches(backend, container, config, record) -> bool:
    if record.protocol != "smb" or record.access_rules or record.access_observations:
        return False
    for share in record.shares:
        if share.kind != "disk" or not config.has_section(share.name):
            return False
        section = config[share.name]
        if share.backing_path and section.get("path", "").rstrip(
            "/"
        ) != share.backing_path.rstrip("/"):
            return False
        for expected, native, default in (
            (share.read_only, "read only", True),
            (share.browseable, "browseable", True),
            (share.guest_ok, "guest ok", False),
        ):
            if (
                expected is not None
                and section.getboolean(native, fallback=default) != expected
            ):
                return False
        users = shlex.split(section.get("valid users", ""))
        if not set(share.valid_groups).issubset(
            {v.removeprefix("@").split("\\")[-1] for v in users if v.startswith("@")}
        ):
            return False
        if not set(share.valid_users).issubset(set(users)):
            return False
        for expected, field in (
            (share.invalid_users, "invalid users"),
            (share.write_users, "write list"),
        ):
            if not set(expected).issubset(shlex.split(section.get(field, ""))):
                return False
    for principal in record.principals:
        database = {"user": "passwd", "group": "group"}.get(principal.kind)
        if (
            database is None
            or native_text(backend, container, ["getent", database, principal.name])
            is None
        ):
            return False
        if (
            principal.external_id
            or principal.local_user_ref
            or principal.directory_subject_ref
        ):
            return False
    return True


def observe_dns_services(
    backend: DeploymentBackend, container: str, runtime: RuntimeConfiguration
) -> object | None:
    """Read BIND's parsed zone inventory."""
    records = runtime.dns_services
    if not records:
        return None
    text = native_text(backend, container, ["named-checkconf", "-l"])
    if text is None:
        return None
    zones = {
        parts[0].rstrip("."): parts[-1]
        for line in text.splitlines()
        if len(parts := line.split()) >= 4
    }
    for record in records:
        if (
            record.implementation != "bind"
            or record.resolver_policy
            or record.dynamic_update
            or record.settings
        ):
            return None
        if any(role != "authoritative" for role in record.roles):
            return None
        for zone in record.zones:
            expected = {"primary": "master", "secondary": "slave"}.get(
                zone.kind, zone.kind
            )
            if (
                zones.get(zone.name.rstrip(".")) != expected
                or zone.rrsets
                or zone.transfer
            ):
                return None
    return _disclose(
        "runtime-dns-services", [r.model_dump(mode="json") for r in records]
    )


def native_json_request(
    backend, container: str, url: str, *, headers=(), method="GET"
) -> object | None:
    """Read a bounded API response with credentials only on curl's stdin."""
    import json

    lines = [
        "silent",
        "show-error",
        "fail",
        "insecure",
        "max-time = 30",
        "max-filesize = 1048576",
        f"request = {json.dumps(method)}",
        f"url = {json.dumps(url)}",
    ]
    lines.extend(f"header = {json.dumps(header)}" for header in headers)
    result = backend.container_exec_with_input(
        container, ["curl", "--config", "-"], "\n".join(lines) + "\n", timeout=35
    )
    if result.returncode != 0 or len(result.stdout) > 1048576:
        return None
    try:
        return json.loads(result.stdout)
    except ValueError, TypeError:
        return None


def container_environment(info) -> dict[str, str]:
    """Read actual environment values for private native queries; never log them."""
    return dict(
        item.split("=", 1)
        for item in info.get("Config", {}).get("Env", ())
        if "=" in item
    )
