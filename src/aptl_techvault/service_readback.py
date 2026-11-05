"""Native readback of Samba and BIND service configuration."""

from __future__ import annotations

import configparser
import re

from aptl_techvault.readback_support import ReadbackBackend, output, require, value


def _samba(backend: ReadbackBackend, container: str) -> configparser.ConfigParser:
    """Read Samba's complete effective configuration through its native parser."""

    text = output(backend, container, ["testparm", "-s", "-v", "--suppress-prompt"])
    result = configparser.ConfigParser(interpolation=None, strict=True)
    result.read_string(text)
    require(result.has_section("global"))
    return result


def identity_authorities(
    backend: ReadbackBackend, node: object
) -> list[dict[str, object]]:
    """Corroborate the served directory realm and its live domain identity."""

    config = _samba(backend, node.container_name)
    info = output(
        backend, node.container_name, ["samba-tool", "domain", "info", "127.0.0.1"]
    )
    fields = {
        key.strip().lower(): val.strip()
        for line in info.splitlines()
        if ":" in line
        for key, val in [line.split(":", 1)]
    }
    result = []
    for authority in node.runtime.identity_authorities:
        row = authority.model_dump(mode="json", by_alias=True)
        require(
            row["kind"] == "domain"
            and config["global"].get("server role", "").lower()
            == "active directory domain controller"
        )
        domain = fields.get("domain", "").lower()
        realm = config["global"].get("realm", "")
        require(domain and realm)
        row["domain_name"], row["realm"] = domain, realm
        row["base_dn"] = ",".join("DC=" + part for part in domain.split("."))
        require(
            not any(
                row[field]
                for field in (
                    "subjects",
                    "policies",
                    "relationships",
                    "resource_scopes",
                    "identity_uses",
                )
            )
        )
        # Native protocol endpoints must be listening, rather than inferred from the domain label.
        listeners = output(backend, node.container_name, ["ss", "-H", "-lnt"])
        for service in row["services"]:
            require(re.search(rf":{int(service['port'])}\s", listeners))
        result.append(row)
    return result


def file_services(backend: ReadbackBackend, node: object) -> list[dict[str, object]]:
    """Translate effective Samba share fields, without trusting source config bytes."""

    config = _samba(backend, node.container_name)
    result = []
    for service in node.runtime.file_services:
        row = service.model_dump(mode="json", by_alias=True)
        require(row["protocol"] == "smb" and not row["access_rules"])
        for share in row["shares"]:
            require(config.has_section(share["name"]))
            observed = config[share["name"]]
            share["backing_path"] = observed.get("path", "")
            for key in ("read_only", "browseable", "guest_ok"):
                native_key = key.replace("_", " ")
                require(native_key in observed)
                share[key] = observed[native_key].lower() in {"yes", "true", "1"}
            users = observed.get("valid users", "").split()
            share["valid_users"] = sorted(
                item for item in users if not item.startswith("@")
            )
            share["valid_groups"] = sorted(
                item[1:] for item in users if item.startswith("@")
            )
            share["invalid_users"] = observed.get("invalid users", "").split()
            share["write_users"] = observed.get("write list", "").split()
        for principal in row["principals"]:
            kind = principal["kind"]
            require(kind in {"group", "user"})
            native = output(
                backend,
                node.container_name,
                ["getent", "group" if kind == "group" else "passwd", principal["name"]],
            )
            require(native.split(":", 1)[0] == principal["name"])
        result.append(row)
    return result


def dns_services(backend: ReadbackBackend, node: object) -> list[dict[str, object]]:
    """Use BIND's parsed configuration and live zone status for each selected zone."""

    config = output(backend, node.container_name, ["named-checkconf", "-p"])
    result = []
    for service in node.runtime.dns_services:
        row = service.model_dump(mode="json", by_alias=True)
        require(value(service.implementation) == "bind")
        require(
            not row["settings"]
            and row["resolver_policy"] is None
            and row["dynamic_update"] is None
        )
        for zone in row["zones"]:
            require(not zone["rrsets"] and zone["transfer"] is None)
            pattern = (
                r'zone\s+"' + re.escape(zone["name"]) + r'"(?:\s+IN)?\s*\{([^}]+)\}'
            )
            match = re.search(pattern, config, re.IGNORECASE)
            require(
                match and re.search(r"type\s+(?:master|primary)\s*;", match.group(1))
            )
            status = output(
                backend, node.container_name, ["rndc", "zonestatus", zone["name"]]
            )
            require("type: primary" in status or "type: master" in status)
            zone["kind"] = "primary"
        result.append(row)
    return result
