"""Publications must prove the owned relay's actual target and host binding."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from aptl.core.deployment._native_range_publications import publication_bindings
from aptl.core.deployment._operator_access_endpoints import OPERATOR_ACCESS_IMAGE
from aptl.core.deployment._compose_resource_ownership import OwnershipConflictError


@pytest.fixture
def observed():
    node = {
        "NetworkSettings": {
            "Networks": {"range": {"IPAddress": "10.77.0.2"}},
            "Ports": {"2022/tcp": None},
        }
    }
    relay = {
        "State": {"Running": True},
        "Config": {
            "Image": OPERATOR_ACCESS_IMAGE,
            "Labels": {
                "lilrae.publication.target": "node-id",
                "lilrae.publication.address": "10.77.0.2",
                "lilrae.publication.port": "2022",
                "lilrae.publication.protocol": "tcp",
            },
            "Env": [
                "APTL_PROXY_TARGET_HOST=10.77.0.2",
                "APTL_PROXY_TARGET_PORT=2022",
                "APTL_PROXY_LISTEN_PORT=2022",
                "LILRAE_PROXY_PROTOCOL=tcp",
            ],
        },
        "NetworkSettings": {
            "Networks": {"range": {}, "apparatus": {}},
            "Ports": {"2022/tcp": [{"HostIp": "127.0.0.1", "HostPort": "32022"}]},
        },
    }
    receipts = [
        SimpleNamespace(
            semantic_name="lilrae-publication-fixture", native_id="relay-id"
        )
    ]
    backend = SimpleNamespace(
        _boundary_receipts={"native-range": {}},
        _resource_ownership=object(),
        _ensure_resource_ownership=lambda: SimpleNamespace(receipts=lambda _: receipts),
        _resolve_owned_container_id=lambda name: name,
        container_inspect=lambda name: node if name == "node-id" else relay,
    )
    return backend, node, relay


def test_actual_relay_publication_preserves_node_topology(observed):
    backend, node, _ = observed
    before = deepcopy(node)
    assert publication_bindings(backend, "node-id") == {
        "2022/tcp": [{"HostIp": "127.0.0.1", "HostPort": "32022"}]
    }
    assert node == before


@pytest.mark.parametrize(
    "mutation", ["environment", "address", "network", "image", "stopped"]
)
def test_label_alone_never_proves_a_relay_target(observed, mutation):
    backend, _, relay = observed
    if mutation == "environment":
        relay["Config"]["Env"][0] = "APTL_PROXY_TARGET_HOST=192.0.2.8"
    elif mutation == "address":
        relay["Config"]["Labels"]["lilrae.publication.address"] = "192.0.2.8"
    elif mutation == "network":
        relay["NetworkSettings"]["Networks"] = {"foreign": {}}
    elif mutation == "image":
        relay["Config"]["Image"] = "foreign:latest"
    else:
        relay["State"]["Running"] = False
    with pytest.raises(OwnershipConflictError):
        publication_bindings(backend, "node-id")


def test_another_nodes_relay_cannot_satisfy_a_publication(observed):
    backend, _, relay = observed
    relay["Config"]["Labels"]["lilrae.publication.target"] = "foreign-id"
    assert publication_bindings(backend, "node-id") == {"2022/tcp": None}


def test_existing_proxy_relays_udp_without_changing_the_payload(monkeypatch):
    import runpy
    import socket
    import threading
    from pathlib import Path

    with (
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as target,
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as front,
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client,
    ):
        for endpoint in (target, front, client):
            endpoint.bind(("127.0.0.1", 0))
            endpoint.settimeout(5)
        monkeypatch.setenv("APTL_PROXY_LISTEN_PORT", str(front.getsockname()[1]))
        monkeypatch.setenv("APTL_PROXY_TARGET_HOST", "127.0.0.1")
        monkeypatch.setenv("APTL_PROXY_TARGET_PORT", str(target.getsockname()[1]))
        module = runpy.run_path(
            str(Path(__file__).parents[1] / "containers/operator-access-proxy/proxy.py")
        )

        def reply():
            payload, address = target.recvfrom(4096)
            target.sendto(payload, address)

        responder = threading.Thread(target=reply)
        responder.start()
        module["_udp_request"](front, b"publication-fixture", client.getsockname())
        assert client.recv(4096) == b"publication-fixture"
        responder.join(timeout=5)
        assert not responder.is_alive()


def test_failed_receipt_removes_only_the_created_relay_and_its_volumes():
    from aptl.core.deployment._native_range_publications import _record_publication

    commands = []

    def refused(_):
        raise OwnershipConflictError("receipt write failed")

    ownership = SimpleNamespace(
        record=refused,
        container_name=lambda _: "relay-fixture",
        workspace_id="fixture",
        project_name="range-fixture",
    )
    backend = SimpleNamespace(
        _resource_attempt_id="attempt-fixture",
        _ownership_daemon_id=lambda: "daemon-fixture",
        _run=lambda argv, **kw: commands.append(argv),
    )
    result = _record_publication(
        backend,
        ownership,
        "relay-fixture",
        SimpleNamespace(address="provision.node.fixture"),
        "created-id",
    )
    assert not result.success
    assert len(commands) == 1
    assert commands[0][-1] == "created-id"
    assert any(flag in commands[0] for flag in ("-v", "--volumes"))


@pytest.mark.parametrize(
    "failure_stage", ["ok", "create", "receipt", "connect", "start", "readback"]
)
def test_publication_requires_policy_receipt_connection_and_effective_readback(
    monkeypatch, failure_stage
):
    from subprocess import CompletedProcess
    from aptl.core.deployment import _native_range_publications as publications
    from aptl.core.deployment.realization import DeploymentPublishedPort

    events = []
    records = []
    port = DeploymentPublishedPort(container_port=2022, host_port=32022)
    node = SimpleNamespace(
        address="provision.node.fixture", container_name="node", published_ports=(port,)
    )

    def record(receipt):
        events.append("receipt")
        if failure_stage == "receipt":
            raise OwnershipConflictError("receipt failed")
        records.append(receipt)

    ownership = SimpleNamespace(
        record=record,
        container_name=lambda _: "relay-fixture",
        labels=lambda **kw: {"owner": "fixture"},
        workspace_id="fixture",
        project_name="range-fixture",
    )

    def command(argv, **kwargs):
        step = argv[2] if argv[1] == "network" else argv[1]
        events.append(step)
        if step == "create":
            assert "floor" in events
            assert "--read-only" in argv
            assert "--cap-drop=ALL" in argv
            assert "APTL_PROXY_TARGET_HOST=10.77.0.2" in argv
        if step == "start":
            assert len(records) == 1
            assert "connect" in events
        return CompletedProcess(argv, int(step == failure_stage), "relay-id", "")

    backend = SimpleNamespace(
        _boundary_receipts={"native-range": {}},
        _project_name="range-fixture",
        _resource_attempt_id="attempt-fixture",
        _ensure_resource_ownership=lambda: ownership,
        _resolve_owned_container_id=lambda _: "node-id",
        _ownership_daemon_id=lambda: "daemon-fixture",
        container_inspect=lambda _: {
            "NetworkSettings": {"Networks": {"range": {"IPAddress": "10.77.0.2"}}}
        },
        _remove_existing_relay=lambda _: None,
        _run=command,
        ensure_generic_base_image=lambda _: [],
        _ensure_operator_access_network=lambda: ("apparatus", []),
    )

    def bindings(*args):
        if "start" in events and failure_stage != "readback":
            return {"2022/tcp": [{"HostIp": "127.0.0.1", "HostPort": "32022"}]}
        return {}

    def floor(*args, **kwargs):
        events.append("floor")

    monkeypatch.setattr(publications, "publication_bindings", bindings)
    monkeypatch.setattr(publications, "refresh_native_policy", floor)
    result = publications.realize_publications(backend, SimpleNamespace(nodes=(node,)))
    assert (result is None) is (failure_stage == "ok")
    if failure_stage in {"create", "receipt", "connect"}:
        assert "start" not in events
    if failure_stage == "receipt":
        assert "rm" in events
