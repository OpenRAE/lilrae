"""Native configuration and running-service observations for the SOC products."""

from __future__ import annotations

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
    """Read the supported native Wazuh agent roster response shapes."""

    roster = json_output(backend, container, ["/var/ossec/bin/agent_control", "-lj"])
    if isinstance(roster, dict):
        roster = roster.get("data", roster.get("affected_items", []))
    if isinstance(roster, dict):
        roster = roster.get("affected_items", [])
    require(isinstance(roster, list))
    return roster


def _wazuh_state(backend, node):
    """Read the native Wazuh version, process status and parsed listener configuration."""

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
    return version, status, root


def _wazuh_components(backend, node, row, status):
    """Read enabled manager components from native running processes."""

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


def _wazuh_content(backend, node, row):
    """Read declared native rule files and require Wazuh parser acceptance."""

    native_files = {}
    for content in row["content_sets"]:
        require(content["file_count"] in {None, len(content["file_refs"])})
        for path in content["file_refs"]:
            require(
                path.startswith(("/var/ossec/etc/rules/", "/var/ossec/etc/decoders/"))
            )
            native_files[path] = output(backend, node.container_name, ["cat", path])
    output(backend, node.container_name, ["/var/ossec/bin/wazuh-analysisd", "-t"])
    return native_files


def _wazuh_rule_groups(document, rule):
    """Read the native group membership of one Wazuh detection rule."""

    groups = set()
    for group in document.iter("group"):
        if rule in list(group):
            groups.update(item for item in group.get("name", "").split(",") if item)
    groups.update(item for item in (rule.findtext("group") or "").split(",") if item)
    return sorted(groups)


def _wazuh_definition(definition, row, native_files):
    """Read one selected native Wazuh detection definition."""

    content = next(
        item
        for item in row["content_sets"]
        if item["content_id"] == definition["content_set_ref"]
    )
    text = "\n".join(native_files[path] for path in content["file_refs"])
    document = ET.fromstring("<root>" + re.sub(r"<\?xml[^>]+\?>", "", text) + "</root>")
    matches = [
        rule
        for rule in document.iter("rule")
        if rule.get("id") == definition["native_id"]
    ]
    require(len(matches) == 1)
    rule = matches[0]
    definition["level"] = int(rule.get("level", "0"))
    definition["name"] = (rule.findtext("description") or "").strip()
    definition["groups"] = _wazuh_rule_groups(document, rule)
    definition["enabled"] = True


def _wazuh_agents(backend, node, row):
    """Require every selected agent in the live Wazuh roster."""

    roster = _agent_roster(backend, node.container_name)
    for agent in row["agents"]:
        require(
            any(
                item.get("name") == agent["name"]
                and str(item.get("status", "")).lower() == "active"
                for item in roster
            )
        )


def _wazuh_listener(backend, node, root, listener):
    """Read the native authentication and transport for one Wazuh listener."""

    role = listener["role"]
    remote_roles = {
        "syslog_ingestion": ("syslog", False),
        "agent_event_ingestion": ("secure", True),
    }
    if role in remote_roles:
        connection, authenticated = remote_roles[role]
        candidates = [
            item
            for item in root.iter("remote")
            if item.findtext("connection") == connection
        ]
        require(candidates)
        default_protocol = "tcp" if authenticated else "udp"
        listener["protocol"] = candidates[0].findtext("protocol", default_protocol)
        listener["auth_required"], listener["tls_enabled"] = authenticated, False
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


def security_monitoring_managers(
    backend: ReadbackBackend, node: object
) -> list[dict[str, object]]:
    """Read Wazuh identity, live processes, roster, rules and listener configuration."""

    version, status, root = _wazuh_state(backend, node)
    result = []
    for manager in node.runtime.security_monitoring_managers:
        row = manager.model_dump(mode="json", by_alias=True)
        require(
            row["implementation"] == "wazuh"
            and version_matches(row["version"], version.group(1))
        )
        _wazuh_components(backend, node, row, status)
        native_files = _wazuh_content(backend, node, row)
        for definition in row["detection_definitions"]:
            _wazuh_definition(definition, row, native_files)
        _wazuh_agents(backend, node, row)
        for listener in row["listeners"]:
            _wazuh_listener(backend, node, root, listener)
        result.append(row)
    return result


def _suricata_config(backend: ReadbackBackend, container: str) -> dict[str, object]:
    """Read Suricata configuration only after its native parser accepts it."""

    path = "/etc/suricata/suricata.yaml"
    output(backend, container, ["suricata", "-T", "-c", path])
    return dict(as_mapping(yaml.safe_load(output(backend, container, ["cat", path]))))


def _suricata_protocols(row, config):
    """Corroborate enabled native application-layer protocols."""

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


def _suricata_networks(row, config):
    """Read native network selector values."""

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


def _suricata_rules(backend, node, row, config):
    """Read accepted native rule sources and rule counts."""

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


def _suricata_outputs(row, config):
    """Read native output paths, event types and enabled state."""

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


def _suricata_controls(backend, node, row, config):
    """Corroborate native enabled control sockets."""

    for channel in row["control_channels"]:
        native = as_mapping(config.get("unix-command"))
        require(native.get("enabled") is True and channel["kind"] == "unix_socket")
        channel["path"] = native.get("filename")
        output(backend, node.container_name, ["test", "-S", channel["path"]])


def network_detection_engines(
    backend: ReadbackBackend, node: object
) -> list[dict[str, object]]:
    """Read Suricata configuration through its native parser and runtime state."""

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
        _suricata_protocols(row, config)
        _suricata_networks(row, config)
        _suricata_rules(backend, node, row, config)
        _suricata_outputs(row, config)
        _suricata_controls(backend, node, row, config)
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


def _docker_control_socket(mount):
    """Recognize native read-write access to the host Docker control socket."""

    return (
        mount.get("Type") == "bind"
        and mount.get("Source") == "/var/run/docker.sock"
        and mount.get("Destination") == "/var/run/docker.sock"
        and mount.get("RW") is True
    )


def _orborus_environment(backend, node):
    """Read only selected native orchestration settings and its control mount."""

    info = as_mapping(backend.container_inspect(node.container_name))
    mounts = info.get("Mounts", [])
    require(any(_docker_control_socket(item) for item in mounts))
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
    return environment


def _orborus_template(backend, template, environment):
    """Corroborate the native workload image selection and pinned local image."""

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


def orchestration_authorities(
    backend: ReadbackBackend, node: object
) -> list[dict[str, object]]:
    """Read Orborus native workload authority and lifecycle configuration."""

    result = []
    for authority in node.runtime.orchestration_authorities:
        row = authority.model_dump(mode="json", by_alias=True)
        require(
            row["engine"] == "docker" and row["control_interface_ref"] == "docker-sock"
        )
        environment = _orborus_environment(backend, node)
        for template in row["spawn_templates"]:
            _orborus_template(backend, template, environment)
        if row["lifecycle_policy"] is not None:
            row["lifecycle_policy"]["execution_timeout"] = environment.get(
                "SHUFFLE_ORBORUS_EXECUTION_TIMEOUT", ""
            )
            row["lifecycle_policy"]["cleanup"] = environment.get("CLEANUP", "")
        if row["scope"] is not None:
            row["scope"]["environment_name"] = environment.get("ENVIRONMENT_NAME", "")
        result.append(row)
    return result
