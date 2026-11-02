"""Native product responses determine the disclosed configuration values."""

import json
from subprocess import CompletedProcess
from types import SimpleNamespace

import pytest
from raes.runtime_configuration import RuntimeConfiguration

from aptl_techvault.application_readback import (
    applications,
    app_authorizations,
    platform_applications,
)
from aptl_techvault.database_readback import datastore_services
from aptl_techvault.readback_support import ReadbackUnavailable
from aptl_techvault.service_readback import (
    dns_services,
    file_services,
    identity_authorities,
)
from aptl_techvault.software_readback import software_components
from aptl_techvault.security_readback import (
    orchestration_authorities,
    network_detection_engines,
    security_monitoring_managers,
)


class NativeBackend:
    def __init__(self, query):
        self.query = query

    def container_exec(self, name, cmd, *, timeout=None):
        assert name == "selected-container" and timeout == 30
        return CompletedProcess(cmd, 0, self.query(cmd), "")


def node(**runtime):
    return SimpleNamespace(
        container_name="selected-container",
        runtime=RuntimeConfiguration.model_validate(runtime),
    )


def test_samba_share_uses_effective_native_permissions():
    selected = node(
        file_services=[
            {
                "file_service_id": "files",
                "protocol": "smb",
                "shares": [
                    {
                        "share_id": "public",
                        "name": "Public",
                        "backing_path": "/declared",
                        "read_only": False,
                        "browseable": True,
                        "guest_ok": True,
                    }
                ],
            }
        ]
    )
    native = "[global]\nserver role = standalone server\n[Public]\npath = /observed\nread only = yes\nbrowseable = no\nguest ok = no\n"
    result = file_services(NativeBackend(lambda _: native), selected)
    share = result[0]["shares"][0]
    assert (
        share["backing_path"],
        share["read_only"],
        share["browseable"],
        share["guest_ok"],
    ) == ("/observed", True, False, False)


def test_directory_domain_is_read_from_the_running_directory():
    selected = node(
        identity_authorities=[
            {
                "identity_authority_id": "directory",
                "kind": "domain",
                "domain_name": "declared.invalid",
                "realm": "DECLARED.INVALID",
            }
        ]
    )

    def query(cmd):
        if cmd[0] == "testparm":
            return "[global]\nserver role = active directory domain controller\nrealm = OBSERVED.INVALID\n"
        return "Domain : observed.invalid\nNetbios domain : OBSERVED\nDC name : dc.observed.invalid\n"

    result = identity_authorities(NativeBackend(query), selected)[0]
    assert (result["domain_name"], result["realm"], result["base_dn"]) == (
        "observed.invalid",
        "OBSERVED.INVALID",
        "DC=observed,DC=invalid",
    )


def test_dns_zone_requires_live_primary_status():
    selected = node(
        dns_services=[
            {
                "dns_service_id": "dns",
                "implementation": "bind",
                "zones": [
                    {"zone_id": "zone", "name": "example.invalid", "kind": "primary"}
                ],
            }
        ]
    )
    state = {"status": "type: primary\nserial: 1\n"}

    def query(cmd):
        return (
            'zone "example.invalid" IN { type primary; file "example.zone"; };'
            if cmd[0] == "named-checkconf"
            else state["status"]
        )

    assert (
        dns_services(NativeBackend(query), selected)[0]["zones"][0]["kind"] == "primary"
    )
    state["status"] = "type: secondary"
    with pytest.raises(ReadbackUnavailable):
        dns_services(NativeBackend(query), selected)


def test_search_partition_counts_come_from_cluster_metadata():
    selected = node(
        datastore_services=[
            {
                "datastore_service_id": "search",
                "engine": "opensearch",
                "version": "2.14.0",
                "partitions": [
                    {
                        "partition_id": "events",
                        "kind": "index",
                        "name": "events",
                        "shard_count": 1,
                        "replica_count": 0,
                    }
                ],
            }
        ]
    )
    responses = {
        "/": {"version": {"number": "2.14.0"}},
        "/_cluster/state/metadata": {
            "metadata": {
                "indices": {
                    "events": {
                        "settings": {
                            "index": {
                                "number_of_shards": "3",
                                "number_of_replicas": "2",
                            }
                        }
                    }
                }
            }
        },
    }
    result = datastore_services(
        NativeBackend(lambda cmd: json.dumps(responses[cmd[-1]])), selected
    )
    assert (
        result[0]["partitions"][0]["shard_count"],
        result[0]["partitions"][0]["replica_count"],
    ) == (3, 2)
    del responses["/_cluster/state/metadata"]["metadata"]["indices"]["events"]
    with pytest.raises(ReadbackUnavailable):
        datastore_services(
            NativeBackend(lambda cmd: json.dumps(responses[cmd[-1]])), selected
        )


def test_application_authentication_is_observed_instead_of_echoed():
    selected = node(
        applications=[
            {
                "application_id": "portal",
                "framework": "flask",
                "routes": [
                    {
                        "route_id": "account",
                        "path": "/account",
                        "methods": ["GET"],
                        "auth_required": True,
                    }
                ],
            }
        ]
    )
    observed = [{"path": "/account", "methods": ["GET"], "auth_required": False}]
    result = applications(NativeBackend(lambda _: json.dumps(observed)), selected)
    assert result[0]["routes"][0]["auth_required"] is False
    with pytest.raises(ReadbackUnavailable):
        applications(NativeBackend(lambda _: "[]"), selected)


@pytest.mark.parametrize(
    "response,expected",
    [("200", False), ("401", True), ("302\nhttps://localhost/users/login", True)],
)
def test_http_authentication_uses_the_native_response(response, expected):
    selected = node(
        applications=[
            {
                "application_id": "dashboard",
                "protocol": "https",
                "service": "web",
                "routes": [
                    {
                        "route_id": "root",
                        "path": "/",
                        "methods": ["GET"],
                        "auth_required": not expected,
                    }
                ],
            }
        ]
    )
    selected.services = [SimpleNamespace(name="web", port=443)]
    result = applications(NativeBackend(lambda _: response), selected)
    assert result[0]["routes"][0]["auth_required"] is expected
    with pytest.raises(ReadbackUnavailable):
        applications(NativeBackend(lambda _: "302\nhttps://localhost/moved"), selected)


def test_component_manifests_are_read_independently_of_the_wazuh_agent():
    selected = node(
        software_components=[
            {
                "component_id": "wazuh-agent",
                "name": "Wazuh agent",
                "version": "4.12.0",
                "component_type": "application",
            },
            {
                "component_id": "library",
                "name": "test-library",
                "version": "1.2.3",
                "component_type": "library",
                "manifest_path": "/opt/library/package-lock.json",
            },
        ]
    )
    native = {
        "name": "test-library",
        "version": "1.2.3",
        "packages": {"": {"name": "test-library", "version": "1.2.3"}},
    }
    result = software_components(NativeBackend(lambda _: json.dumps(native)), selected)
    assert [item["component_id"] for item in result] == ["library"]
    native["version"] = "9.0.0"
    with pytest.raises(ReadbackUnavailable):
        software_components(NativeBackend(lambda _: json.dumps(native)), selected)


def test_orchestration_observes_daemon_configuration_and_local_image_presence():
    selected = node(
        orchestration_authorities=[
            {
                "orchestration_authority_id": "orborus",
                "control_interface_ref": "docker-sock",
                "engine": "docker",
                "scope": {"environment_name": "Declared"},
                "lifecycle_policy": {"execution_timeout": "600"},
                "spawn_templates": [
                    {
                        "template_id": "shuffle-http-1-4-0",
                        "image_ref": "frikky/shuffle:http_1.4.0@sha256:" + "a" * 64,
                    },
                    {"template_id": "shuffle-worker", "image_ref": "declared-worker"},
                ],
            }
        ]
    )
    info = {
        "Mounts": [
            {
                "Type": "bind",
                "Source": "/var/run/docker.sock",
                "Destination": "/var/run/docker.sock",
                "RW": True,
            }
        ],
        "Config": {
            "Env": [
                "SHUFFLE_BASE_IMAGE_NAME=frikky/shuffle",
                "SHUFFLE_WORKER_IMAGE=observed-worker",
                "SHUFFLE_ORBORUS_EXECUTION_TIMEOUT=120",
                "CLEANUP=true",
                "ENVIRONMENT_NAME=Observed",
            ]
        },
    }
    backend = SimpleNamespace(
        container_inspect=lambda _: info,
        substrate_image_identity=lambda _: (
            "sha256:" + "b" * 64,
            "application/vnd.oci.image.config.v1+json",
        ),
    )
    result = orchestration_authorities(backend, selected)[0]
    assert result["spawn_templates"][1]["image_ref"] == "observed-worker"
    assert result["lifecycle_policy"]["execution_timeout"] == "120"
    assert result["scope"]["environment_name"] == "Observed"
    backend.substrate_image_identity = lambda _: None
    with pytest.raises(ReadbackUnavailable):
        orchestration_authorities(backend, selected)


def test_suricata_observes_output_types_and_rejects_missing_rule_source():
    selected = node(
        network_detection_engines=[
            {
                "network_detection_engine_id": "ids",
                "implementation": "suricata",
                "version": "7.0",
                "rule_sources": [
                    {"source_id": "local", "kind": "local", "name": "local.rules"}
                ],
                "output_streams": [
                    {
                        "stream_id": "events",
                        "format": "eve_json",
                        "event_types": ["alert"],
                        "enabled": True,
                    }
                ],
            }
        ]
    )
    config = {
        "rule-files": ["local.rules"],
        "outputs": [
            {
                "eve-log": {
                    "enabled": True,
                    "filename": "eve.json",
                    "types": ["dns", {"http": {"extended": True}}],
                }
            }
        ],
    }

    def query(cmd):
        return "Suricata version 7.0.10" if cmd[-1] == "-V" else json.dumps(config)

    result = network_detection_engines(NativeBackend(query), selected)[0]
    assert result["output_streams"][0]["event_types"] == ["dns", "http"]
    config["rule-files"] = []
    with pytest.raises(ReadbackUnavailable):
        network_detection_engines(NativeBackend(query), selected)


def test_wazuh_observes_nested_agent_roster_and_running_components():
    selected = node(
        security_monitoring_managers=[
            {
                "security_monitoring_manager_id": "manager",
                "implementation": "wazuh",
                "version": "4.12.0",
                "agents": [{"agent_id": "agent", "name": "observed-agent"}],
                "components": [
                    {
                        "component_id": "analysis",
                        "kind": "analysis_engine",
                        "name": "wazuh-analysisd",
                        "enabled": True,
                    }
                ],
            }
        ]
    )
    state = {"status": "active"}

    def query(cmd):
        if cmd[-1] == "info":
            return 'WAZUH_VERSION="v4.12.0"'
        if cmd[-1] == "status":
            return "wazuh-analysisd is stopped"
        if cmd[-1] == "-lj":
            return json.dumps(
                {
                    "data": {
                        "affected_items": [
                            {"name": "observed-agent", "status": state["status"]}
                        ]
                    }
                }
            )
        return "<ossec_config/>"

    assert (
        security_monitoring_managers(NativeBackend(query), selected)[0]["components"][
            0
        ]["enabled"]
        is False
    )
    state["status"] = "disconnected"
    with pytest.raises(ReadbackUnavailable):
        security_monitoring_managers(NativeBackend(query), selected)


def test_misp_cache_endpoint_requires_native_corroboration():
    selected = node(
        platform_applications=[
            {
                "platform_application_id": "misp",
                "product": "MISP",
                "version": "2.5.50",
                "upstream_bindings": [
                    {
                        "binding_id": "cache",
                        "role": "data_source",
                        "target_node_ref": "misp-redis",
                    }
                ],
            }
        ]
    )
    state = {"cache": "misp-redis"}

    def query(cmd):
        if cmd[0] == "printenv":
            return state["cache"]
        if "VERSION.json" in cmd[-1]:
            return json.dumps({"major": "2", "minor": "5", "hotfix": "50"})
        return "misp-db"

    assert platform_applications(NativeBackend(query), selected)
    state["cache"] = "unrelated-cache"
    with pytest.raises(ReadbackUnavailable):
        platform_applications(NativeBackend(query), selected)


def test_misp_read_only_api_key_restricts_its_administrator_owner():
    selected = node(
        app_authorizations=[
            {
                "app_authorization_id": "misp",
                "resource_vocabulary": "app_resource",
                "auth_enabled": True,
                "principals": [
                    {"principal_id": "misp-suricata-sync-api-key", "kind": "api_key"}
                ],
                "roles": [{"role_id": "reader"}],
                "role_mappings": [
                    {
                        "mapping_id": "reader-mapping",
                        "role_ref": "reader",
                        "users": ["misp-suricata-sync-api-key"],
                    }
                ],
                "permission_grants": [
                    {
                        "grant_id": "read",
                        "role_ref": "reader",
                        "resource_kind": "app_resource",
                        "actions": ["read"],
                        "resource_patterns": ["events/*", "attributes/*"],
                        "effect": "allow",
                    }
                ],
            }
        ]
    )
    native = {
        "users": [{"id": "1", "perm_auth": "1", "perm_site_admin": "1"}],
        "keys": [
            {"user_id": "1", "comment": "techvault-suricata-sync", "read_only": "1"}
        ],
    }
    assert app_authorizations(NativeBackend(lambda _: json.dumps(native)), selected)
    native["keys"][0]["read_only"] = "0"
    with pytest.raises(ReadbackUnavailable):
        app_authorizations(NativeBackend(lambda _: json.dumps(native)), selected)
