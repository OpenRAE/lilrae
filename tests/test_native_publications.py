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
