"""Initial Redis and OpenSearch inventory using native configuration and APIs."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

import re
from urllib.parse import quote

from aptl.backends._runtime_concern_disclosure import _disclose
from aptl.backends.database_inventory import version_matches
from aptl.backends.service_inventory import (
    container_environment,
    native_json_request,
    native_text,
)
from aptl.core.deployment._application_account_requests import basic_authorization
from aptl.core.deployment._misp_cache_credential import MISP_CACHE_RUNTIME_CONFIG_PATH
from aptl.core.deployment._wazuh_attestation import declared_wazuh_facts_match


def observe_datastores(backend, node, nodes) -> object | None:
    records = node.runtime.datastore_services
    if not records:
        return None
    info = backend.container_inspect(node.container_name)
    for record in records:
        if record.engine == "redis":
            matched = _redis_matches(backend, node, info, record)
        elif record.engine == "opensearch":
            matched = _opensearch_matches(backend, node, nodes, record)
        else:
            matched = False
        if not matched:
            return None
    return _disclose(
        "runtime-datastore-services", [r.model_dump(mode="json") for r in records]
    )


def _redis_matches(backend, node, info, record) -> bool:
    version = native_text(backend, node.container_name, ["redis-server", "--version"])
    match = re.search(r"\bv=([^ ]+)", version or "")
    if match is None or not version_matches(match[1], record.version):
        return False
    if record.data_model != "key_value" or any(
        (
            record.cluster,
            record.partitions,
            record.templates,
            record.mappings,
            record.settings,
        )
    ):
        return False
    data = backend.container_file_read(
        node.container_name, MISP_CACHE_RUNTIME_CONFIG_PATH, max_bytes=65536
    )
    if data is None:
        return False
    config = dict(
        line.split(None, 1)
        for line in data.decode().splitlines()
        if line.strip() and not line.startswith("#")
    )
    command = info.get("Config", {}).get("Cmd", ())
    if MISP_CACHE_RUNTIME_CONFIG_PATH not in command:
        return False
    persistence = record.persistence
    if persistence is not None and (
        persistence.aof is not None
        and (config.get("appendonly", "no") == "yes") != persistence.aof
        or persistence.eviction != config.get("maxmemory-policy", "noeviction")
    ):
        return False
    return _endpoints_match(backend, node, record.nodes)


def _endpoints_match(backend, node, declared) -> bool:
    sockets = backend.observe_container_listeners(node.container_name)
    if sockets is None:
        return False
    for member in declared:
        for endpoint in member.endpoints:
            if not any(
                protocol == "tcp" and port == endpoint.port
                for protocol, _host, port in sockets.sockets
            ):
                return False
    return True


def _opensearch_matches(backend, node, nodes, record) -> bool:
    if record.data_model != "search_index":
        return False
    # Wazuh's product version differs from its embedded OpenSearch version.
    # Its immutable selected image and the ordinary readiness owner's native
    # API facts already validate this product and all selected index metadata.
    if node.image is not None and node.image.source_name == "wazuh/wazuh-indexer":
        return (
            node.image.source_version == record.version
            and declared_wazuh_facts_match(
                backend.declared_wazuh_attestation,
                node.backend_services[0] if len(node.backend_services) == 1 else None,
                node,
            )
        )
    client = next(
        (
            n
            for n in nodes
            if n.runtime is not None
            and any(
                b.target_node_ref == node.name
                for app in n.runtime.platform_applications
                for b in app.upstream_bindings
            )
        ),
        None,
    )
    if client is None:
        return False
    env = container_environment(backend.container_inspect(client.container_name))
    url = env.get("SHUFFLE_OPENSEARCH_URL", "")
    if not url or "SHUFFLE_OPENSEARCH_PASSWORD" not in env:
        return False
    header = basic_authorization(
        env.get("SHUFFLE_OPENSEARCH_USERNAME", ""), env["SHUFFLE_OPENSEARCH_PASSWORD"]
    )

    # Shuffle's backend image has no curl. The datastore supplies its native
    # client, while its selected client's actual endpoint and credentials are
    # sent privately over stdin.
    def query(path):
        return native_json_request(
            backend, node.container_name, url.rstrip("/") + path, headers=(header,)
        )

    root = query("/")
    if not isinstance(root, dict) or not version_matches(
        root.get("version", {}).get("number", ""), record.version
    ):
        return False
    native = query("/_nodes/_local")
    members = list(native.get("nodes", {}).values()) if isinstance(native, dict) else []
    if (
        len(members) != 1
        or not _node_matches(record.nodes, members[0])
        or not _endpoints_match(backend, node, record.nodes)
    ):
        return False
    for partition in record.partitions:
        state = query("/" + quote(partition.name, safe="") + "/_settings")
        settings = (
            state.get(partition.name, {}).get("settings", {}).get("index", {})
            if isinstance(state, dict)
            else {}
        )
        if str(settings.get("number_of_shards")) != str(partition.shard_count) or str(
            settings.get("number_of_replicas")
        ) != str(partition.replica_count):
            return False
    for mapping in record.mappings:
        payload = query("/" + quote(mapping.name, safe="") + "/_mapping")
        properties = (
            payload.get(mapping.name, {}).get("mappings", {}).get("properties")
            if isinstance(payload, dict)
            else None
        )
        if (
            not isinstance(properties, dict)
            or mapping.top_level_field_count is not None
            and len(properties) != mapping.top_level_field_count
        ):
            return False
    security = record.transport_security
    if security is not None and (
        security.mode != "tls"
        or not url.startswith("https://")
        or security.client_verification
        != (env.get("SHUFFLE_OPENSEARCH_SKIPSSL_VERIFY", "false").lower() != "true")
    ):
        return False
    return not any(
        (
            record.cluster,
            record.templates,
            record.settings,
            record.aliases,
            record.lifecycle_policies,
            record.ingest_pipelines,
            record.backup_targets,
        )
    )


def _node_matches(declared, actual) -> bool:
    for member in declared:
        if member.name and member.name != actual.get("name"):
            return False
        if not set(member.roles).issubset(actual.get("roles", ())):
            return False
        if member.is_coordinator is False:
            return False  # every OpenSearch node coordinates requests
    return True
