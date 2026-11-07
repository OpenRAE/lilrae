"""Exercise native readback and failure reporting for the startup service surface."""

import json
from types import SimpleNamespace

from raes.runtime_configuration import RuntimeConfiguration
from raes_contracts.vocabulary import ObservationStrength

from aptl.backends._raes_observation_helpers import ObservedResource
from aptl.backends._raes_runtime_capabilities import CORE_RUNTIME_CONCERN_SOURCES
from aptl.backends.application_inventory import observe_applications
from aptl.backends.datastore_inventory import observe_datastores
from aptl.backends.detection_inventory import observe_detection_engines, observe_sensors
from aptl.backends.initial_service_inventory import (
    RUNTIME_SERVICE_READERS,
    observe_initial_services,
)
from aptl.backends.monitoring_inventory import observe_monitoring_managers
from aptl.backends.orchestration_inventory import observe_orchestration_authorities
from aptl.backends.raes_realization_model import NodeRealization
from aptl.backends.service_inventory import native_json_request
from aptl.core.deployment._proc_net_listeners import ContainerListeners


def node(runtime, **kwargs):
    return NodeRealization(
        address="provision.node.service",
        name="service",
        aliases=(),
        profiles=(),
        backend_services=("service",),
        container_name="service",
        services=(),
        networks=(),
        static_addresses=(),
        runtime=RuntimeConfiguration.model_validate(runtime),
        **kwargs,
    )


class Native:
    def __init__(self):
        self.stdout = ""
        self.code = 1
        self.info = {}
        self.files = {}
        self.replies = {}
        self.inputs = []
        self.sockets = ContainerListeners()
        self.image = ("sha256:" + "1" * 64, "image")

    def container_inspect(self, _):
        return self.info

    def container_file_read(self, _, path, *, max_bytes):
        return self.files.get(path)

    def container_exec(self, name, argv, *, timeout):
        value = next(
            (value for key, value in self.replies.items() if key in " ".join(argv)),
            None,
        )
        return SimpleNamespace(
            returncode=0 if value is not None else 1, stdout=value or ""
        )

    def container_exec_with_input(self, name, argv, payload, *, timeout):
        self.inputs.append((argv, payload))
        reply = next(
            (value for key, value in self.replies.items() if key in payload), None
        )
        return SimpleNamespace(
            returncode=0 if reply is not None else self.code,
            stdout=json.dumps(reply) if reply is not None else self.stdout,
        )

    def observe_container_listeners(self, _):
        return self.sockets

    def recorded_docker_source(self, _):
        return None

    def substrate_image_identity(self, _):
        return self.image


def test_runtime_capabilities_use_guest_readers_and_skip_unrealized_nodes():
    assert all(
        CORE_RUNTIME_CONCERN_SOURCES[k] == (
            ObservationStrength.DAEMON_OBSERVED
            if k == "runtime-orchestration-authorities"
            else ObservationStrength.GUEST_OBSERVED
        )
        for k in RUNTIME_SERVICE_READERS
    )
    n = node({"dns_services": [{"dns_service_id": "dns", "implementation": "bind"}]})
    observations = {n.address: ObservedResource(False)}
    backend = Native()
    observe_initial_services(backend, SimpleNamespace(nodes=(n,)), observations)
    assert observations[n.address].concerns == {}


def test_native_api_never_puts_authorization_in_argv():
    backend = Native()
    backend.code, backend.stdout = 0, '{"ready":true}'
    assert native_json_request(
        backend, "service", "https://localhost/", headers=("Authorization: fixture",)
    ) == {"ready": True}
    argv, payload = backend.inputs[0]
    assert argv == ["curl", "--config", "-"]
    assert "Authorization: fixture" in payload
    backend.stdout = "x" * (1048576 + 1)
    assert native_json_request(backend, "service", "https://localhost/") is None
    backend.stdout = "not-json"
    assert native_json_request(backend, "service", "https://localhost/") is None


def test_flask_route_methods_and_authentication_are_not_assumed():
    n = node(
        {
            "applications": [
                {
                    "application_id": "app",
                    "framework": "flask",
                    "protocol": "http",
                    "routes": [
                        {
                            "route_id": "private",
                            "path": "/private",
                            "methods": ["GET"],
                            "auth_required": True,
                        }
                    ],
                }
            ]
        },
        backend_provider_kind="python-flask-application",
        backend_provider_parameters=(("workdir", "/app"), ("module", "app:app")),
    )
    backend = Native()
    backend.code = 0
    backend.stdout = json.dumps(
        [{"path": "/private", "methods": ["GET"], "auth_required": True}]
    )
    assert observe_applications(backend, n, (n,)) is not None
    backend.stdout = json.dumps(
        [{"path": "/private", "methods": ["GET"], "auth_required": False}]
    )
    assert observe_applications(backend, n, (n,)) is None
    backend.stdout = json.dumps(
        [{"path": "/other", "methods": ["GET"], "auth_required": True}]
    )
    assert observe_applications(backend, n, (n,)) is None


def test_redis_reads_actual_persistence_configuration():
    from aptl.core.deployment._misp_cache_credential import (
        MISP_CACHE_RUNTIME_CONFIG_PATH,
    )

    n = node(
        {
            "datastore_services": [
                {
                    "datastore_service_id": "cache",
                    "engine": "redis",
                    "data_model": "key_value",
                    "version": "7",
                    "persistence": {
                        "persistence_id": "cache-state",
                        "aof": False,
                        "eviction": "noeviction",
                    },
                }
            ]
        }
    )
    backend = Native()
    backend.info = {"Config": {"Cmd": ["redis-server", MISP_CACHE_RUNTIME_CONFIG_PATH]}}
    backend.files[MISP_CACHE_RUNTIME_CONFIG_PATH] = (
        b"appendonly no\nmaxmemory-policy noeviction\n"
    )
    backend.replies["redis-server"] = "Redis server v=7.4.1 sha=abc bits=64"
    assert observe_datastores(backend, n, (n,)) is not None
    backend.files[MISP_CACHE_RUNTIME_CONFIG_PATH] = (
        b"appendonly yes\nmaxmemory-policy noeviction\n"
    )
    assert observe_datastores(backend, n, (n,)) is None


def test_suricata_requires_live_capture_and_selected_network_attachment():
    n = node(
        {
            "network_sensors": [
                {
                    "network_sensor_id": "sensor",
                    "implementation": "suricata",
                    "sensor_kind": "ids",
                    "monitoring_posture": "passive",
                    "monitored_network_refs": ["dmz-net"],
                }
            ]
        }
    )
    backend = Native()
    backend.info = {"NetworkSettings": {"Networks": {"project_aptl-dmz": {}}}}
    backend.replies = {
        "iface-list": '{"return":"OK","message":{"ifaces":["any"]}}',
        "capture-mode": '{"return":"OK","message":"PCAP_DEV"}',
    }
    assert observe_sensors(backend, n, (n,)) is not None
    backend.info = {}
    assert observe_sensors(backend, n, (n,)) is None


def test_suricata_rejects_failed_or_wrong_version_ruleset():
    n = node(
        {
            "network_detection_engines": [
                {
                    "network_detection_engine_id": "ids",
                    "implementation": "suricata",
                    "engine_kind": "ids",
                    "version": "8.0",
                    "configuration_file_refs": ["/etc/suricata/config.yaml"],
                }
            ]
        }
    )
    backend = Native()
    backend.files["/etc/suricata/config.yaml"] = b"app-layer: {protocols: {}}\n"
    backend.replies = {
        "version": '{"return":"OK","message":"8.0.1 RELEASE"}',
        "ruleset-stats": '{"return":"OK","message":[{"rules_loaded":10,"rules_failed":0}]}',
    }
    assert observe_detection_engines(backend, n, (n,)) is not None
    backend.replies["ruleset-stats"] = (
        '{"return":"OK","message":[{"rules_loaded":10,"rules_failed":1}]}'
    )
    assert observe_detection_engines(backend, n, (n,)) is None
    backend.replies["version"] = '{"return":"OK","message":"7.0.9 RELEASE"}'
    assert observe_detection_engines(backend, n, (n,)) is None


def test_wazuh_requires_authenticated_api_and_running_component():
    n = node(
        {
            "security_monitoring_managers": [
                {
                    "security_monitoring_manager_id": "manager",
                    "implementation": "wazuh",
                    "manager_kind": "siem",
                    "version": "4.12.0",
                    "components": [
                        {
                            "component_id": "analysis",
                            "name": "wazuh-analysisd",
                            "enabled": True,
                        }
                    ],
                }
            ]
        }
    )
    backend = Native()
    backend.info = {"Config": {"Env": ["API_USERNAME=fixture", "API_PASSWORD=fixture"]}}
    backend.files["/var/ossec/etc/ossec.conf"] = b"<ossec_config/>"
    backend.replies = {
        "/security/user/authenticate": {"data": {"token": "fixture-token"}},
        "/manager/status": {
            "error": 0,
            "data": {"affected_items": [{"wazuh-analysisd": "running"}]},
        },
        "/agents?": {"error": 0, "data": {"affected_items": []}},
        "wazuh-control": 'WAZUH_VERSION="v4.12.0"',
    }
    assert observe_monitoring_managers(backend, n, (n,)) is not None
    backend.replies["/manager/status"]["data"]["affected_items"][0][
        "wazuh-analysisd"
    ] = "stopped"
    assert observe_monitoring_managers(backend, n, (n,)) is None
    backend.replies["/security/user/authenticate"] = {"error": 1}
    assert observe_monitoring_managers(backend, n, (n,)) is None


def test_orchestration_requires_socket_policy_and_available_spawn_image():
    n = node(
        {
            "local_control_interfaces": [
                {
                    "control_interface_id": "docker",
                    "kind": "unix_socket",
                    "path": "/var/run/docker.sock",
                    "access": "read_write",
                }
            ],
            "orchestration_authorities": [
                {
                    "orchestration_authority_id": "worker",
                    "engine": "docker",
                    "privilege_class": "host_root_equivalent",
                    "control_interface_ref": "docker",
                    "scope": {"environment_name": "Lab"},
                    "lifecycle_policy": {
                        "execution_timeout": "600",
                        "cleanup": "false",
                    },
                    "spawn_templates": [
                        {"template_id": "worker-image", "image_ref": "example/worker:1"}
                    ],
                }
            ],
        }
    )
    backend = Native()
    backend.info = {
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
                "ENVIRONMENT_NAME=Lab",
                "SHUFFLE_ORBORUS_EXECUTION_TIMEOUT=600",
                "CLEANUP=false",
            ]
        },
    }
    assert observe_orchestration_authorities(backend, n, (n,)) is not None
    backend.image = None
    assert observe_orchestration_authorities(backend, n, (n,)) is None
    backend.image = ("sha256:" + "1" * 64, "image")
    backend.info["Mounts"][0]["RW"] = False
    assert observe_orchestration_authorities(backend, n, (n,)) is None
