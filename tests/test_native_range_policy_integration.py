"""Real packet and kernel readback proof using disposable Docker bridges."""

import hashlib
import json
import socket
import subprocess
import uuid
from pathlib import Path

import pytest

from aptl.core.deployment._compose_boundary import (
    DEFAULT_BOUNDARY_HELPER_IMAGE,
    _helper_command,
)
from aptl.core.deployment.boundary import (
    BoundaryNetwork,
    NativeRangeAllowance,
    NativeRangeBoundarySpec,
)

pytestmark = pytest.mark.integration
IMAGE = DEFAULT_BOUNDARY_HELPER_IMAGE


def run(*args, payload=None, check=True):
    result = subprocess.run(
        list(args), input=payload, capture_output=True, text=True, timeout=180
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def mutate(action, policy):
    return run(*_helper_command(action, IMAGE), payload=policy.canonical_json())


def probe(container, address, port):
    code = "import socket,sys; s=socket.create_connection((sys.argv[1],int(sys.argv[2])),timeout=1); s.close()"
    return (
        run(
            "docker",
            "exec",
            container,
            "python3",
            "-c",
            code,
            address,
            str(port),
            check=False,
        ).returncode
        == 0
    )


def test_native_range_packets_and_owned_restart():
    root = Path(__file__).parents[1]
    run(
        "docker",
        "build",
        "-t",
        IMAGE,
        "-f",
        str(root / "containers/network-boundary-helper/Dockerfile"),
        str(root),
    )
    prefix = "lilrae-968-" + uuid.uuid4().hex[:8]
    inside, outside = prefix + "-in", prefix + "-out"
    client, peer, target = prefix + "-client", prefix + "-peer", prefix + "-target"
    policy = None
    listener = socket.socket()
    host_listener = socket.socket()
    try:
        segment = uuid.uuid4().hex[:4]
        run(
            "docker",
            "network",
            "create",
            "--ipv6",
            "--subnet",
            f"fd96:8:{segment}::/64",
            inside,
        )
        run(
            "docker",
            "network",
            "create",
            "--opt",
            "com.docker.network.bridge.gateway_mode_ipv4=routed",
            "--opt",
            "com.docker.network.bridge.gateway_mode_ipv6=routed",
            "--ipv6",
            "--subnet",
            f"fd96:9:{segment}::/64",
            outside,
        )
        for name, network, ports in (
            (client, inside, []),
            (peer, inside, ["-p", "127.0.0.1::8080"]),
            (target, outside, ["-p", "8080", "-p", "8081", "-p", "53:53/udp"]),
        ):
            code = """
import http.server, socket, threading
class Server(http.server.HTTPServer):
    address_family = socket.AF_INET6
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/redirect':
            self.send_response(302)
            self.send_header('Location', 'http://' + self.connection.getsockname()[0].removeprefix('::ffff:') + ':8081/')
        else:
            self.send_response(200)
        self.end_headers()
def dns():
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(('0.0.0.0', 53))
    while True:
        data, peer = server.recvfrom(4096)
        server.sendto(data, peer)
threading.Thread(target=dns, daemon=True).start()
threading.Thread(target=Server(('::',8080),Handler).serve_forever,daemon=True).start()
Server(('::',8081),Handler).serve_forever()
"""
            run(
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "--network",
                network,
                *ports,
                "--entrypoint",
                "python3",
                IMAGE,
                "-c",
                code,
            )
        inspect = json.loads(run("docker", "network", "inspect", inside).stdout)[0]
        bridge = "br-" + inspect["Id"][:12]
        ipv4 = next(
            item for item in inspect["IPAM"]["Config"] if ":" not in item["Subnet"]
        )
        subnet = ipv4["Subnet"]
        gateway = ipv4["Gateway"]

        def address(name, network):
            return json.loads(run("docker", "inspect", name).stdout)[0][
                "NetworkSettings"
            ]["Networks"][network]["IPAddress"]

        external = address(target, outside)
        internal = address(peer, inside)
        route = run(
            "docker",
            "run",
            "--rm",
            "--network",
            "host",
            "--entrypoint",
            "ip",
            IMAGE,
            "-j",
            "route",
            "get",
            "198.18.0.1",
        )
        host_address = json.loads(route.stdout)[0]["prefsrc"]
        # Bind only the two exact addresses exercised by the host-access probes.
        listener.bind((gateway, 0))
        listener.listen()
        host_port = listener.getsockname()[1]
        host_listener.bind((host_address, host_port))
        host_listener.listen()
        assert probe(client, host_address, host_port), (
            "host interface fixture must answer before enforcement"
        )
        external6 = json.loads(run("docker", "inspect", target).stdout)[0][
            "NetworkSettings"
        ]["Networks"][outside]["GlobalIPv6Address"]
        assert probe(client, external6, 8080), (
            "IPv6 fixture must be reachable before enforcement"
        )

        def dns_probe():
            code = "import socket,sys; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(1); s.sendto(b'968-dns-probe',(sys.argv[1],53)); assert s.recv(4096)==b'968-dns-probe'"
            return (
                run(
                    "docker",
                    "exec",
                    client,
                    "python3",
                    "-c",
                    code,
                    external,
                    check=False,
                ).returncode
                == 0
            )

        assert dns_probe(), "DNS fixture must answer before enforcement"
        assert probe(client, external, 8080), (
            "external fixture must be reachable before enforcement"
        )
        assert probe(client, gateway, host_port), (
            "host fixture must be reachable before enforcement"
        )
        policy = NativeRangeBoundarySpec(
            prefix,
            (
                BoundaryNetwork(
                    "security-net",
                    bridge,
                    ipv4_cidr=subnet,
                    ipv4_gateway=gateway,
                    ipv6_cidr=f"fd96:8:{segment}::/64",
                ),
            ),
        )
        mutate("check", policy)
        mutate("apply", policy)
        assert not probe(client, external, 8080)
        assert not dns_probe()
        assert not probe(client, external6, 8080)
        assert not probe(client, gateway, host_port)
        assert not probe(client, host_address, host_port)
        assert not probe(client, gateway, 2375)
        assert probe(client, internal, 8080)
        # External DNS, direct IP and IPv6 cannot acquire an implicit grant.
        assert not probe(client, "192.0.2.8", 443)
        assert not probe(client, "2001:db8::8", 443)
        dns = run(
            "docker",
            "exec",
            client,
            "python3",
            "-c",
            "import socket; socket.setdefaulttimeout(1); socket.getaddrinfo('blocked-968.invalid',443)",
            check=False,
        )
        assert dns.returncode != 0
        # Containers have no host socket authority, independent of TCP policy.
        socket_probe = run(
            "docker",
            "exec",
            client,
            "python3",
            "-c",
            "import socket; s=socket.socket(socket.AF_UNIX); s.connect('/var/run/docker.sock')",
            check=False,
        )
        assert socket_probe.returncode != 0
        allowed = NativeRangeBoundarySpec(
            prefix,
            policy.networks,
            (
                NativeRangeAllowance(external, "tcp", 8080),
                NativeRangeAllowance(external, "udp", 53),
                NativeRangeAllowance(external6, "tcp", 8080),
            ),
        )
        mutate("apply", allowed)
        mutate("observe", allowed)
        assert probe(client, external, 8080)
        assert not probe(client, external, 8081)
        assert probe(client, internal, 8080)
        assert dns_probe()
        assert probe(client, external6, 8080)
        assert not probe(client, external6, 8081)
        redirect = "import urllib.request,sys; urllib.request.urlopen('http://'+sys.argv[1]+':8080/redirect',timeout=1)"
        assert (
            run(
                "docker",
                "exec",
                client,
                "python3",
                "-c",
                redirect,
                external,
                check=False,
            ).returncode
            != 0
        )
        # Mutation proof: preserve rule markers but alter the actual verdict.
        table = (
            "aptl_bnd_"
            + hashlib.sha256(f"{prefix}:native-range".encode()).hexdigest()[:12]
        )
        nft = [
            "docker",
            "run",
            "--rm",
            "--network",
            "host",
            "--cap-add=NET_ADMIN",
            "--entrypoint",
            "nft",
            IMAGE,
        ]
        payload = json.loads(run(*nft, "-j", "list", "table", "inet", table).stdout)
        rule = next(
            item["rule"]
            for item in payload["nftables"]
            if "rule" in item and item["rule"]["chain"] == "forward"
        )
        run(
            *nft,
            "replace",
            "rule",
            "inet",
            table,
            "forward",
            "handle",
            str(rule["handle"]),
            "accept",
            "comment",
            json.dumps(rule["comment"]),
        )
        observed = run(
            *_helper_command("observe", IMAGE),
            payload=allowed.canonical_json(),
            check=False,
        )
        assert observed.returncode != 0, (
            "readback must reject an altered verdict even with its original marker"
        )
        # Reapplying replaces only this owner's table and remains observable.
        mutate("apply", allowed)
        mutate("observe", allowed)
        published = json.loads(run("docker", "inspect", peer).stdout)[0][
            "NetworkSettings"
        ]["Ports"]["8080/tcp"][0]["HostPort"]
        code = "import socket; socket.create_connection(('127.0.0.1',int(__import__('sys').argv[1])),timeout=2).close()"
        run("python3", "-c", code, published)
        # A connection from the range to that publication is blocked before DNAT.
        assert not probe(client, gateway, int(published))
    finally:
        listener.close()
        host_listener.close()
        for name in (client, peer, target):
            run("docker", "rm", "-f", name, check=False)
        if policy is not None:
            mutate("cleanup", policy)
        for network in (inside, outside):
            run("docker", "network", "rm", network, check=False)
