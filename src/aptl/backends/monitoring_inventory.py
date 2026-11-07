"""Initial Wazuh manager inventory through its native API and configuration."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aptl.backends.raes_realization_model import NodeRealization
    from aptl.core.deployment.backend import DeploymentBackend

from pathlib import PurePosixPath
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

from aptl.backends._runtime_concern_disclosure import _disclose
from aptl.backends.service_inventory import (
    container_environment,
    native_json_request,
    native_text,
)
from aptl.core.deployment._application_account_requests import basic_authorization


def observe_monitoring_managers(
    backend: DeploymentBackend, node: NodeRealization, nodes: Sequence[NodeRealization]
) -> object | None:
    records = node.runtime.security_monitoring_managers
    if not records:
        return None
    env = container_environment(backend.container_inspect(node.container_name))
    if not env.get("API_USERNAME") or not env.get("API_PASSWORD"):
        return None
    url = "https://localhost:55000"
    login = native_json_request(
        backend,
        node.container_name,
        url + "/security/user/authenticate",
        headers=(basic_authorization(env["API_USERNAME"], env["API_PASSWORD"]),),
        method="POST",
    )
    token = login.get("data", {}).get("token") if isinstance(login, dict) else None
    if not token:
        return None

    def query(path):
        payload = native_json_request(
            backend,
            node.container_name,
            url + path,
            headers=("Authorization: Bearer " + token,),
        )
        return (
            payload.get("data", {}).get("affected_items")
            if isinstance(payload, dict) and payload.get("error") == 0
            else None
        )

    status = query("/manager/status")
    agents = query("/agents?limit=500")
    raw = backend.container_file_read(
        node.container_name, "/var/ossec/etc/ossec.conf", max_bytes=1048576
    )
    if not status or agents is None or raw is None:
        return None
    try:
        config = ET.fromstring(b"<root>" + raw + b"</root>")
    except ET.ParseError:
        return None
    for record in records:
        if record.implementation != "wazuh" or record.manager_kind != "siem":
            return None
        version = native_text(
            backend, node.container_name, ["/var/ossec/bin/wazuh-control", "info"]
        )
        if version is None or f'WAZUH_VERSION="v{record.version}"' not in version:
            return None
        if not _components_match(backend, node, record, status[0]):
            return None
        if not _agents_match(record, agents):
            return None
        if not _listeners_match(backend, node, record, config):
            return None
        if not _content_matches(record, query) or not _definitions_match(record, query):
            return None
    return _disclose(
        "runtime-security-monitoring-managers",
        [r.model_dump(mode="json") for r in records],
    )


def _components_match(backend, node, record, status):
    for component in record.components:
        running = status.get(component.name) == "running"
        if component.name == "filebeat":
            running = (
                native_text(backend, node.container_name, ["pgrep", "-x", "filebeat"])
                is not None
            )
        if component.enabled is not None and running != component.enabled:
            return False
    return True


def _agents_match(record, agents):
    for agent in record.agents:
        found = next((a for a in agents if a.get("name") == agent.name), None)
        if (
            found is None
            or agent.status != "unknown"
            and found.get("status") != agent.status
        ):
            return False
    return True


def _content_matches(record, query):
    for content in record.content_sets:
        resource = (
            "rules"
            if content.kind == "rule_corpus"
            else "decoders"
            if content.kind == "decoder_corpus"
            else None
        )
        if (
            resource is None
            or content.file_count is not None
            and content.file_count != len(content.file_refs)
        ):
            return False
        for path in content.file_refs:
            files = query(
                "/"
                + resource
                + "/files?"
                + urlencode({"filename": PurePosixPath(path).name})
            )
            found = next(
                (
                    f
                    for f in files or ()
                    if f.get("filename") == PurePosixPath(path).name
                ),
                None,
            )
            if (
                found is None
                or content.loaded is not None
                and (found.get("status") == "enabled") != content.loaded
            ):
                return False
    return True


def _definitions_match(record, query):
    for definition in record.detection_definitions:
        rules = query("/rules?" + urlencode({"rule_ids": definition.native_id}))
        found = next(
            (r for r in rules or () if str(r.get("id")) == definition.native_id),
            None,
        )
        if (
            found is None
            or definition.level is not None
            and found.get("level") != definition.level
            or not set(definition.groups).issubset(found.get("groups", ()))
        ):
            return False
        if definition.loaded is False or definition.enabled is False:
            return False
    return True


def _listeners_match(backend, node, record, config) -> bool:
    observed = backend.observe_container_listeners(node.container_name)
    if observed is None:
        return False
    services = {s.name: s.port for s in node.services}
    remote = config.findall(".//remote")
    for listener in record.listeners:
        port = services.get(listener.service)
        if not any(
            protocol == listener.protocol and p == port
            for protocol, _host, p in observed.sockets
        ):
            return False
        if listener.role in {"agent_event_ingestion", "syslog_ingestion"}:
            connection = (
                "secure" if listener.role == "agent_event_ingestion" else "syslog"
            )
            if not any(
                r.findtext("connection") == connection
                and int(r.findtext("port", "0")) == port
                for r in remote
            ):
                return False
            expected_auth, expected_tls = connection == "secure", False
        elif listener.role in {"agent_enrollment", "api"}:
            expected_auth, expected_tls = True, True
            if (
                listener.role == "agent_enrollment"
                and config.findtext(".//auth/disabled", "no") != "no"
            ):
                return False
        else:
            return False
        if (
            listener.auth_required is not None
            and listener.auth_required != expected_auth
            or listener.tls_enabled is not None
            and listener.tls_enabled != expected_tls
        ):
            return False
    return True
