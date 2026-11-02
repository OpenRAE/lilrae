"""Native configuration and running-service observations for the SOC products."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

import yaml

from aptl_techvault.readback_support import (
    ReadbackBackend,
    as_mapping,
    json_output,
    output,
    require,
    version_matches,
)


def _agent_roster(backend: ReadbackBackend, container: str) -> list[dict[str, object]]:
    roster = json_output(backend, container, ["/var/ossec/bin/agent_control", "-lj"])
    if isinstance(roster, dict):
        roster = roster.get("data", roster.get("affected_items", []))
    if isinstance(roster, dict):
        roster = roster.get("affected_items", [])
    require(isinstance(roster, list))
    return roster


def security_monitoring_managers(
    backend: ReadbackBackend, node: object
) -> list[dict[str, object]]:
    """Read Wazuh's version, live processes, roster, rules and listener config."""

    info = output(
        backend, node.container_name, ["/var/ossec/bin/wazuh-control", "info"]
    )
    version = re.search(r'WAZUH_VERSION="v([^"\n]+)"', info)
    require(version)
    status = output(
        backend, node.container_name, ["/var/ossec/bin/wazuh-control", "status"]
    )
    config = output(backend, node.container_name, ["cat", "/var/ossec/etc/ossec.conf"])
    root = ET.fromstring("<root>" + re.sub(r"<\?xml[^>]+\?>", "", config) + "</root>")
    result = []
    for manager in node.runtime.security_monitoring_managers:
        row = manager.model_dump(mode="json", by_alias=True)
        require(
            row["implementation"] == "wazuh"
            and version_matches(row["version"], version.group(1))
        )
        for component in row["components"]:
            name = component["name"]
            if name == "filebeat":
                running = bool(
                    output(backend, node.container_name, ["pgrep", "-x", "filebeat"])
                )
            else:
                running = (
                    f"{name} is running" in status or f"{name} is running..." in status
                )
            component["enabled"] = running
        native_files = {}
        for content in row["content_sets"]:
            require(content["file_count"] in {None, len(content["file_refs"])})
            for path in content["file_refs"]:
                require(
                    path.startswith(
                        ("/var/ossec/etc/rules/", "/var/ossec/etc/decoders/")
                    )
                )
                native_files[path] = output(backend, node.container_name, ["cat", path])
        output(backend, node.container_name, ["/var/ossec/bin/wazuh-analysisd", "-t"])
        for definition in row["detection_definitions"]:
            content = next(
                item
                for item in row["content_sets"]
                if item["content_id"] == definition["content_set_ref"]
            )
            text = "\n".join(native_files[path] for path in content["file_refs"])
            document = ET.fromstring(
                "<root>" + re.sub(r"<\?xml[^>]+\?>", "", text) + "</root>"
            )
            matches = [
                rule
                for rule in document.iter("rule")
                if rule.get("id") == definition["native_id"]
            ]
            require(len(matches) == 1)
            rule = matches[0]
            definition["level"] = int(rule.get("level", "0"))
            definition["name"] = (rule.findtext("description") or "").strip()
            groups = set()
            for group in document.iter("group"):
                if rule in list(group):
                    groups.update(
                        item for item in group.get("name", "").split(",") if item
                    )
            groups.update(
                item for item in (rule.findtext("group") or "").split(",") if item
            )
            definition["groups"] = sorted(groups)
            definition["enabled"] = True
        roster = _agent_roster(backend, node.container_name)
        for agent in row["agents"]:
            require(
                any(
                    item.get("name") == agent["name"]
                    and str(item.get("status", "")).lower() == "active"
                    for item in roster
                )
            )
        for listener in row["listeners"]:
            role = listener["role"]
            if role == "syslog_ingestion":
                candidates = [
                    item
                    for item in root.iter("remote")
                    if item.findtext("connection") == "syslog"
                ]
                require(candidates)
                listener["protocol"] = candidates[0].findtext("protocol", "udp")
                listener["auth_required"], listener["tls_enabled"] = False, False
            elif role == "agent_event_ingestion":
                candidates = [
                    item
                    for item in root.iter("remote")
                    if item.findtext("connection") == "secure"
                ]
                require(candidates)
                listener["protocol"] = candidates[0].findtext("protocol", "tcp")
                listener["auth_required"], listener["tls_enabled"] = True, False
            elif role == "agent_enrollment":
                candidates = list(root.iter("auth"))
                require(candidates and candidates[0].findtext("disabled", "no") == "no")
                listener["auth_required"], listener["tls_enabled"] = True, True
            elif role == "api":
                status = output(
                    backend,
                    node.container_name,
                    [
                        "curl",
                        "-sk",
                        "--max-time",
                        "20",
                        "--output",
                        "/dev/null",
                        "--write-out",
                        "%{http_code}",
                        "https://127.0.0.1:55000/",
                    ],
                )
                require(status in {"401", "403"})
                listener["auth_required"], listener["tls_enabled"] = True, True
            else:
                require(False)
        result.append(row)
    return result


def _suricata_config(backend: ReadbackBackend, container: str) -> dict[str, object]:
    path = "/etc/suricata/suricata.yaml"
    output(backend, container, ["suricata", "-T", "-c", path])
    return dict(as_mapping(yaml.safe_load(output(backend, container, ["cat", path]))))


def network_detection_engines(
    backend: ReadbackBackend, node: object
) -> list[dict[str, object]]:
    """Read Suricata's accepted rule sources, address sets, outputs and control socket."""

    config = _suricata_config(backend, node.container_name)
    reported = output(backend, node.container_name, ["suricata", "-V"])
    version = re.search(r"(?:version|Suricata)\s+([0-9.]+)", reported)
    require(version)
    result = []
    for engine in node.runtime.network_detection_engines:
        row = engine.model_dump(mode="json", by_alias=True)
        require(
            row["implementation"] == "suricata"
            and version_matches(row["version"], version.group(1))
        )
        protocols = (
            as_mapping(as_mapping(config.get("app-layer")).get("protocols"))
            if row["app_layer_protocols"]
            else {}
        )
        for protocol in row["app_layer_protocols"]:
            require(
                as_mapping(protocols.get(protocol)).get("enabled")
                in {True, "yes", "detection-only"}
            )
        groups = (
            as_mapping(as_mapping(config.get("vars")).get("address-groups"))
            if row["network_sets"]
            else {}
        )
        for group in row["network_sets"]:
            native = str(groups.get(group["name"], ""))
            group["selector_values"] = [
                item.strip() for item in native.strip("[]").split(",") if item.strip()
            ]
        for source in row["rule_sources"]:
            require(source["name"] in config.get("rule-files", []))
            contents = [
                output(backend, node.container_name, ["cat", path])
                for path in source["file_refs"]
            ]
            if source["rule_count"] is not None:
                source["rule_count"] = sum(
                    len(re.findall(r"\bsid:\s*\d+\s*;", text)) for text in contents
                )
        outputs = {}
        for record in config.get("outputs", []):
            outputs.update(as_mapping(record))
        for stream in row["output_streams"]:
            key = "eve-log" if stream["format"] == "eve_json" else "fast"
            native = as_mapping(outputs.get(key))
            stream["enabled"] = native.get("enabled") is True
            if key == "eve-log":
                stream["event_types"] = sorted(
                    event if isinstance(event, str) else next(iter(as_mapping(event)))
                    for event in native.get("types", [])
                )
            else:
                stream["event_types"] = ["alert"]
            filename = str(native.get("filename", ""))
            stream["path"] = (
                filename
                if filename.startswith("/")
                else str(config.get("default-log-dir", "/var/log/suricata")).rstrip("/")
                + "/"
                + filename
            )
        for channel in row["control_channels"]:
            native = as_mapping(config.get("unix-command"))
            require(native.get("enabled") is True and channel["kind"] == "unix_socket")
            channel["path"] = native.get("filename")
            output(backend, node.container_name, ["test", "-S", channel["path"]])
        result.append(row)
    return result


def network_sensors(backend: ReadbackBackend, node: object) -> list[dict[str, object]]:
    """Read the running Suricata capture mode rather than trusting its label."""

    processes = output(backend, node.container_name, ["ps", "-eo", "args"])
    capture = [
        line
        for line in processes.splitlines()
        if "suricata" in line
        and (" -i " in line or "--af-packet" in line or " -q " in line)
    ]
    require(len(capture) == 1)
    result = []
    for sensor in node.runtime.network_sensors:
        row = sensor.model_dump(mode="json", by_alias=True)
        require(row["implementation"] == "suricata")
        row["monitoring_posture"] = "inline" if " -q " in capture[0] else "passive"
        result.append(row)
    return result


def orchestration_authorities(
    backend: ReadbackBackend, node: object
) -> list[dict[str, object]]:
    """Read Orborus' effective workload image and lifecycle environment."""

    result = []
    for authority in node.runtime.orchestration_authorities:
        row = authority.model_dump(mode="json", by_alias=True)
        require(
            row["engine"] == "docker" and row["control_interface_ref"] == "docker-sock"
        )
        info = as_mapping(backend.container_inspect(node.container_name))
        mounts = info.get("Mounts", [])
        require(
            any(
                item.get("Type") == "bind"
                and item.get("Source") == "/var/run/docker.sock"
                and item.get("Destination") == "/var/run/docker.sock"
                and item.get("RW") is True
                for item in mounts
            )
        )
        config = as_mapping(info.get("Config"))
        keys = {
            "SHUFFLE_WORKER_IMAGE",
            "SHUFFLE_BASE_IMAGE_NAME",
            "SHUFFLE_ORBORUS_EXECUTION_TIMEOUT",
            "CLEANUP",
            "ENVIRONMENT_NAME",
        }
        environment = {
            key: val
            for line in config.get("Env", [])
            if "=" in line
            for key, val in [line.split("=", 1)]
            if key in keys
        }
        for template in row["spawn_templates"]:
            if template["template_id"] == "shuffle-worker":
                template["image_ref"] = environment.get("SHUFFLE_WORKER_IMAGE", "")
            else:
                # Corroborate the configured app repository and the local pinned
                # image. The identity API returns a config id and media type,
                # which are different from a registry manifest digest.
                require(template["template_id"] == "shuffle-http-1-4-0")
                require(
                    template["image_ref"].split("@", 1)[0]
                    == environment.get("SHUFFLE_BASE_IMAGE_NAME", "") + ":http_1.4.0"
                )
                identity = backend.substrate_image_identity(template["image_ref"])
                require(
                    identity
                    and identity[0].startswith("sha256:")
                    and identity[1] == "application/vnd.oci.image.config.v1+json"
                )
        if row["lifecycle_policy"] is not None:
            row["lifecycle_policy"]["execution_timeout"] = environment.get(
                "SHUFFLE_ORBORUS_EXECUTION_TIMEOUT", ""
            )
            row["lifecycle_policy"]["cleanup"] = environment.get("CLEANUP", "")
        if row["scope"] is not None:
            row["scope"]["environment_name"] = environment.get("ENVIRONMENT_NAME", "")
        result.append(row)
    return result
