"""Exercise real Unix HTTP transport without contacting the host Docker daemon."""

from contextlib import closing, contextmanager
import http.client
from http.server import BaseHTTPRequestHandler
import json
from itertools import count
from pathlib import Path
import socket
import socketserver
import tempfile
import threading

import pytest

from tests.test_lilrae_docker_recording import _store
from aptl.core.deployment._compose_resource_ownership import OwnershipConflictError


class _UnixHTTP(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.host)


@contextmanager
def fake_docker(*, inspection_gate=None, supervision_entered=None, creation_status=201):
    calls = []
    containers = {}
    identifiers = count(1)
    inspections = count(1)
    with tempfile.TemporaryDirectory(prefix="lilrae-api-test-") as directory:
        upstream = Path(directory) / "engine.sock"

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                pass

            def do_GET(self):
                if self.path == "/upgrade":
                    self.send_response(101)
                    self.send_header("Connection", "Upgrade")
                    self.send_header("Upgrade", "tcp")
                    self.end_headers()
                    self.wfile.flush()
                    self.connection.sendall(self.connection.recv(4))
                    self.close_connection = True
                elif self.path.startswith("/containers/"):
                    if inspection_gate is not None:
                        if next(inspections) >= 2 and supervision_entered is not None:
                            supervision_entered.set()
                        inspection_gate.wait(8)
                    native_id = self.path.split("/")[2]
                    self.reply(
                        200 if native_id in containers else 404,
                        containers.get(native_id, {}),
                    )
                elif self.path == "/stream":
                    self.send_response(200)
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    self.wfile.write(b"3\r\none\r\n3\r\ntwo\r\n0\r\n\r\n")
                    self.wfile.flush()
                else:
                    self.reply(200, {"ID": "daemon-1"})

            def do_POST(self):
                payload = json.loads(
                    self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}"
                )
                calls.append((self.path, payload))
                if self.path.startswith("/v1.44/containers/create"):
                    native_id = f"{next(identifiers):064x}"
                    containers[native_id] = {
                        "Id": native_id,
                        "Platform": "linux",
                        "Image": "sha256:" + "b" * 64,
                        "State": {"Status": "created", "Running": False},
                    }
                    self.reply(
                        creation_status,
                        {"Id": native_id}
                        if creation_status == 201
                        else {"message": "upstream create failed"},
                    )
                elif self.path.startswith("/containers/"):
                    native_id = self.path.split("/")[2]
                    running = "/start" in self.path
                    if native_id in containers:
                        containers[native_id]["State"] = {
                            "Running": running,
                            "Status": "running" if running else "exited",
                        }
                    self.reply(204, {})
                else:
                    self.reply(200, {"accepted": True})

            def reply(self, status, payload):
                body = b"" if status == 204 else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True

        with Server(str(upstream), Handler) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                endpoints = Path(directory) / "recording"
                endpoints.mkdir(mode=0o700)
                yield upstream, endpoints, calls
            finally:
                server.shutdown()
                worker.join(3)


def call(endpoint, method, path, payload=None, *, timeout=3):
    with closing(_UnixHTTP(str(endpoint), timeout=timeout)) as client:
        body = None if payload is None else json.dumps(payload)
        client.request(
            method, path, body=body, headers={"Content-Type": "application/json"}
        )
        response = client.getresponse()
        return response.status, response.read()


@pytest.mark.parametrize("target", ["/other-operation", "/v1.44/containers/create"])
def test_waiting_client_receives_continue_before_sending_its_body(tmp_path, target):
    import h11
    from aptl.core.deployment.lilrae_docker_http import HTTPPeer
    from aptl.core.deployment.lilrae_docker_relay import DockerRecordingRelay

    with fake_docker() as (upstream, endpoints, _calls):
        with DockerRecordingRelay(_store(tmp_path), upstream, endpoints) as relay:
            endpoint = relay.endpoint("provision.node.holder", timeout_seconds=60)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
                stream.settimeout(1)
                stream.connect(str(endpoint))
                client = HTTPPeer(stream, h11.CLIENT)
                client.send(
                    h11.Request(
                        method=b"POST",
                        target=target.encode(),
                        headers=[
                            (b"host", b"docker"),
                            (b"content-length", b"2"),
                            (b"expect", b"100-continue"),
                        ],
                    )
                )
                interim = client.receive()
                assert isinstance(interim, h11.InformationalResponse)
                assert interim.status_code == 100
                client.send(h11.Data(data=b"{}"))
                client.send(h11.EndOfMessage())
                response = client.receive()
                assert isinstance(response, h11.Response)
                assert response.status_code in {200, 201}


def test_transitive_socket_delegation_records_each_daemon_response(tmp_path):
    from aptl.core.deployment.lilrae_docker_relay import DockerRecordingRelay

    store = _store(tmp_path)
    secret = "must-not-be-retained-in-recorder-state"
    with fake_docker() as (upstream, endpoints, calls):
        with DockerRecordingRelay(store, upstream, endpoints) as relay:
            root = relay.endpoint("provision.node.holder", timeout_seconds=60)
            request = {
                "Image": "same-image",
                "Env": [f"PASSWORD={secret}"],
                "HostConfig": {
                    "Binds": ["/var/run/docker.sock:/var/run/docker.sock:rw"],
                    "Privileged": True,
                },
            }
            status, body = call(
                root, "POST", "/v1.44/containers/create?name=worker", request
            )
            assert status == 201
            parent_id = json.loads(body)["Id"]
            delegated = Path(calls[0][1]["HostConfig"]["Binds"][0].split(":")[0])
            assert delegated != Path("/var/run/docker.sock")
            assert delegated != root
            assert calls[0][1]["HostConfig"]["Privileged"] is True
            status, body = call(
                delegated, "POST", "/v1.44/containers/create", {"Image": "same-image"}
            )
            assert status == 201
            child = store.creation(json.loads(body)["Id"])
            assert child.parent_native_id == parent_id
            assert child.source_address == "provision.node.holder"
            assert len(store.ownership.receipts("container")) == 2
    assert all(
        secret.encode() not in path.read_bytes() for path in tmp_path.rglob("*.json")
    )


def test_cooperative_recording_preserves_other_docker_operations(tmp_path):
    from aptl.core.deployment.lilrae_docker_relay import DockerRecordingRelay

    store = _store(tmp_path)
    with fake_docker() as (upstream, endpoints, calls):
        with DockerRecordingRelay(store, upstream, endpoints) as relay:
            endpoint = relay.endpoint("provision.node.holder", timeout_seconds=60)
            assert call(endpoint, "GET", "/stream") == (200, b"onetwo")
            assert (
                call(endpoint, "POST", "/unrestricted", {"arbitrary": True})[0] == 200
            )
            assert calls == [("/unrestricted", {"arbitrary": True})]
    assert store.records() == ()


def test_http_upgrade_supports_bidirectional_bytes(tmp_path):
    from aptl.core.deployment.lilrae_docker_relay import DockerRecordingRelay

    with fake_docker() as (upstream, endpoints, _calls):
        with DockerRecordingRelay(_store(tmp_path), upstream, endpoints) as relay:
            endpoint = relay.endpoint("provision.node.holder", timeout_seconds=60)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(3)
                client.connect(str(endpoint))
                client.sendall(
                    b"GET /upgrade HTTP/1.1\r\nHost: docker\r\nConnection: Upgrade\r\nUpgrade: tcp\r\n\r\n"
                )
                response = b""
                while b"\r\n\r\n" not in response:
                    response += client.recv(4096)
                assert b"101" in response.split(b"\r\n", 1)[0]
                client.sendall(b"ping")
                assert client.recv(4) == b"ping"


def test_two_concurrent_attempts_with_identical_images_do_not_share_ownership(tmp_path):
    from aptl.core.deployment.lilrae_docker_relay import DockerRecordingRelay

    stores = [_store(tmp_path / str(i), attempt=f"attempt-{i}") for i in range(2)]
    with fake_docker() as (upstream, endpoints, _calls):
        with DockerRecordingRelay(stores[0], upstream, endpoints / "a") as first:
            with DockerRecordingRelay(stores[1], upstream, endpoints / "b") as second:
                roots = [
                    relay.endpoint("provision.node.holder", timeout_seconds=60)
                    for relay in (first, second)
                ]
                threads = [
                    threading.Thread(
                        target=call,
                        args=(
                            root,
                            "POST",
                            "/v1.44/containers/create",
                            {"Image": "same-image"},
                        ),
                    )
                    for root in roots
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(3)
                (first_record,) = stores[0].records()
                (second_record,) = stores[1].records()
                assert first_record.native_id != second_record.native_id
                with pytest.raises(OwnershipConflictError):
                    stores[0].creation(second_record.native_id)


def test_delegating_an_existing_recorded_socket_keeps_immediate_parent_identity(
    tmp_path,
):
    from aptl.core.deployment.lilrae_docker_relay import DockerRecordingRelay

    store = _store(tmp_path)
    with fake_docker() as (upstream, endpoints, calls):
        with DockerRecordingRelay(store, upstream, endpoints) as relay:
            root = relay.endpoint("provision.node.holder", timeout_seconds=60)
            request = {
                "Image": "same-image",
                "HostConfig": {
                    "Binds": ["/var/run/docker.sock:/var/run/docker.sock:rw"]
                },
            }
            call(root, "POST", "/v1.44/containers/create", request)
            parent_socket = calls[0][1]["HostConfig"]["Binds"][0].split(":")[0]
            request["HostConfig"]["Binds"] = [
                f"{parent_socket}:/var/run/docker.sock:rw"
            ]
            _, body = call(parent_socket, "POST", "/v1.44/containers/create", request)
            child_id = json.loads(body)["Id"]
            child_socket = calls[1][1]["HostConfig"]["Binds"][0].split(":")[0]
            assert child_socket != parent_socket
            _, body = call(
                child_socket, "POST", "/v1.44/containers/create", {"Image": "leaf"}
            )
            assert store.creation(json.loads(body)["Id"]).parent_native_id == child_id


def test_uncertain_create_error_keeps_an_intent_without_guessing_a_native_id(tmp_path):
    from aptl.core.deployment.lilrae_docker_relay import DockerRecordingRelay

    store = _store(tmp_path)
    with fake_docker(creation_status=500) as (upstream, endpoints, _calls):
        with DockerRecordingRelay(store, upstream, endpoints) as relay:
            endpoint = relay.endpoint("provision.node.holder", timeout_seconds=60)
            assert (
                call(
                    endpoint, "POST", "/v1.44/containers/create", {"Image": "example"}
                )[0]
                == 500
            )
    assert store.pending()
    assert store.ownership.receipts("container") == ()


def test_other_allocating_api_calls_are_forwarded_with_a_recording_gap(tmp_path):
    from aptl.core.deployment.lilrae_docker_relay import DockerRecordingRelay

    store = _store(tmp_path)
    with fake_docker() as (upstream, endpoints, _calls):
        with DockerRecordingRelay(store, upstream, endpoints) as relay:
            endpoint = relay.endpoint("provision.node.holder", timeout_seconds=60)
            assert (
                call(endpoint, "POST", "/v1.44/services/create", {"Name": "service"})[0]
                == 200
            )
    assert "opaque-native-allocation" in store.gaps()


def test_large_create_carriers_are_forwarded_without_silently_claiming_coverage(
    tmp_path,
):
    from aptl.core.deployment.lilrae_docker_relay import DockerRecordingRelay
    from aptl.core.deployment.lilrae_docker_http import INSPECTION_LIMIT

    store = _store(tmp_path)
    with fake_docker() as (upstream, endpoints, _calls):
        with DockerRecordingRelay(store, upstream, endpoints) as relay:
            endpoint = relay.endpoint("provision.node.holder", timeout_seconds=60)
            assert (
                call(
                    endpoint,
                    "POST",
                    "/v1.44/containers/create",
                    {"Image": "example", "Env": ["TEST=" + "x" * INSPECTION_LIMIT]},
                )[0]
                == 201
            )
    assert len(store.records()) == 1
    assert "create-request-uninspected" in store.gaps()
