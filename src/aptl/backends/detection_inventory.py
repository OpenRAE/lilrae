"""Initial Suricata configuration and loaded-rules readback."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aptl.backends.raes_realization_model import NodeRealization
    from aptl.core.deployment.backend import DeploymentBackend

import ast
import json
from pathlib import PurePosixPath

import yaml

from aptl.backends._runtime_concern_disclosure import _disclose
from aptl.backends.database_inventory import version_matches
from aptl.backends.service_inventory import native_text


def _command(
    backend, container, command, path="/var/run/suricata/suricata-command.socket"
):
    text = native_text(backend, container, ["suricatasc", "-c", command, path])
    if text is None or len(text) > 1048576:
        return None
    try:
        result = json.loads(text)
    except ValueError:
        result = ast.literal_eval(text)
    return (
        result.get("message")
        if isinstance(result, dict) and result.get("return") == "OK"
        else None
    )


def observe_sensors(
    backend: DeploymentBackend, node: NodeRealization, nodes: Sequence[NodeRealization]
) -> object | None:
    records = node.runtime.network_sensors
    if not records:
        return None
    interfaces = _command(backend, node.container_name, "iface-list")
    mode = _command(backend, node.container_name, "capture-mode")
    info = backend.container_inspect(node.container_name)
    attached = info.get("NetworkSettings", {}).get("Networks", {})
    for sensor in records:
        if (
            sensor.implementation != "suricata"
            or sensor.sensor_kind != "ids"
            or sensor.monitoring_posture != "passive"
        ):
            return None
        if interfaces is None or "pcap" not in str(mode).lower():
            return None
        names = interfaces.get("ifaces", ()) if isinstance(interfaces, dict) else ()
        if not set(sensor.capture_interfaces).issubset(names):
            return None
        for reference in sensor.monitored_network_refs:
            if not any(
                name.endswith("-" + reference.removesuffix("-net")) or name == reference
                for name in attached
            ):
                return None
    return _disclose(
        "runtime-network-sensors", [r.model_dump(mode="json") for r in records]
    )


def observe_detection_engines(
    backend: DeploymentBackend, node: NodeRealization, nodes: Sequence[NodeRealization]
) -> object | None:
    records = node.runtime.network_detection_engines
    if not records:
        return None
    for engine in records:
        if (
            engine.implementation != "suricata"
            or engine.engine_kind != "ids"
            or len(engine.configuration_file_refs) != 1
        ):
            return None
        version = _command(backend, node.container_name, "version")
        if not isinstance(version, str) or not version_matches(
            version.split()[0], engine.version
        ):
            return None
        path = engine.configuration_file_refs[0]
        data = backend.container_file_read(node.container_name, path, max_bytes=1048576)
        config = yaml.safe_load(data) if data else None
        if not isinstance(config, dict) or not _configuration_matches(
            backend, node, engine, config
        ):
            return None
        stats = _command(backend, node.container_name, "ruleset-stats")
        if (
            not isinstance(stats, list)
            or not stats
            or any(
                s.get("rules_failed", 0) != 0 or s.get("rules_loaded", 0) < 1
                for s in stats
            )
        ):
            return None
    return _disclose(
        "runtime-network-detection-engines",
        [r.model_dump(mode="json") for r in records],
    )


def _configuration_matches(backend, node, engine, config):
    protocols = config.get("app-layer", {}).get("protocols", {})
    if any(
        protocols.get(p, {}).get("enabled") not in (True, "yes", "detection-only")
        for p in engine.app_layer_protocols
    ):
        return False
    groups = config.get("vars", {}).get("address-groups", {})
    for network in engine.network_sets:
        actual = str(groups.get(network.name, ""))
        for name, value in groups.items():
            if actual == "!$" + name:
                actual = "!" + str(value).strip("[]")
        if set(actual.strip("[]").split(",")) != set(network.selector_values):
            return False
    return (
        _rules_match(backend, node, engine, config)
        and _outputs_match(engine, config)
        and _controls_match(backend, node, engine)
    )


def _rules_match(backend, node, engine, config):
    selected = {
        str(
            PurePosixPath(config.get("default-rule-path", "/var/lib/suricata/rules"))
            / path
        )
        if not path.startswith("/")
        else path
        for path in config.get("rule-files", ())
    }
    for source in engine.rule_sources:
        if (
            source.format != "suricata_rule"
            or source.loaded is False
            or not set(source.file_refs).issubset(selected)
        ):
            return False
        count = 0
        for path in source.file_refs:
            data = backend.container_file_read(
                node.container_name, path, max_bytes=16 * 1024 * 1024
            )
            if data is None:
                return False
            count += sum(
                bool(line.strip()) and not line.lstrip().startswith(b"#")
                for line in data.splitlines()
            )
        if source.rule_count is not None and source.rule_count != count:
            return False
    return True


def _outputs_match(engine, config):
    outputs = {
        key: value
        for entry in config.get("outputs", ())
        for key, value in entry.items()
    }
    for stream in engine.output_streams:
        settings = outputs.get(
            {"eve_json": "eve-log", "fast_log": "fast"}.get(stream.format)
        )
        if not isinstance(settings, dict) or settings.get("enabled") != stream.enabled:
            return False
        path = str(
            PurePosixPath(config.get("default-log-dir", "/var/log/suricata"))
            / settings.get("filename", "")
        )
        if path != stream.path:
            return False
        events = {
            e if isinstance(e, str) else next(iter(e))
            for e in settings.get("types", ())
        }
        if stream.format == "fast_log":
            events = {"alert"}
        if not set(stream.event_types).issubset(events):
            return False
    return True


def _controls_match(backend, node, engine):
    sockets = backend.observe_container_listeners(node.container_name)
    for channel in engine.control_channels:
        if (
            channel.kind != "unix_socket"
            or channel.auth_required is True
            or sockets is None
            or channel.path not in sockets.unix_socket_paths
        ):
            return False
        commands = _command(backend, node.container_name, "command-list", channel.path)
        names = commands.get("commands", ()) if isinstance(commands, dict) else ()
        if any(
            c != "rule_reload"
            or not {"reload-rules", "ruleset-reload-rules"}.intersection(names)
            for c in channel.capabilities
        ):
            return False
    return True
