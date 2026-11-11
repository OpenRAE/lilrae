"""HTTP/1.1 framing and raw upgrade relay using h11's public state machine."""

from __future__ import annotations

from collections.abc import Callable
import http.client
import json
import os
import select
import socket

import h11

from aptl.core.deployment._compose_resource_ownership import OwnershipConflictError
from aptl.core.deployment._docker_endpoint_binding import _local_docker_socket_identity
from aptl.core.deployment._cleanup_budget import cleanup_command_timeout


class _UnixConnection(http.client.HTTPConnection):
    """Send HTTP requests to a Docker daemon through a Unix socket."""

    def connect(self) -> None:
        """Open the Unix socket that the host field names."""
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.host)


class NativeDocker:
    """Bounded native reads/actions with conclusive absence distinct from errors."""

    def __init__(
        self,
        socket_path: str | os.PathLike[str],
        daemon_id: str,
        *,
        identity: tuple[int, int] | None = None,
    ) -> None:
        """Bind the daemon socket, its expected ID, and its socket identity."""
        self.socket_path = str(socket_path)
        self.daemon_id = daemon_id
        self.identity = identity or _local_docker_socket_identity(self.socket_path)

    def request(self, method: str, path: str) -> tuple[int, dict[str, object]]:
        """Send one bounded request and return the status and the JSON object."""
        if (
            self.identity is None
            or _local_docker_socket_identity(self.socket_path) != self.identity
        ):
            raise OwnershipConflictError("recording daemon endpoint changed")
        connection = _UnixConnection(self.socket_path, timeout=cleanup_command_timeout(5))
        try:
            connection.request(method, path)
            response = connection.getresponse()
            body = response.read(INSPECTION_LIMIT + 1)
            cleanup_command_timeout(5)
            if len(body) > INSPECTION_LIMIT:
                raise OwnershipConflictError(
                    "recording native response is uninspectable"
                )
            value = json.loads(body) if body else {}
            if not isinstance(value, dict):
                raise ValueError("recording native response is uninspectable")
            return response.status, value
        except (ValueError, http.client.HTTPException) as exc:
            raise OwnershipConflictError(
                "recording native response is unavailable"
            ) from exc
        finally:
            connection.close()

    def verify_daemon(self) -> None:
        """Make sure that the socket still serves the expected daemon."""
        status, info = self.request("GET", "/info")
        if status != 200 or info.get("ID") != self.daemon_id:
            raise OwnershipConflictError("recording daemon identity changed")

    def inspect(self, native_id: str) -> dict[str, object] | None:
        """Return the container inspection, or None when the container is absent."""
        self.verify_daemon()
        status, info = self.request("GET", f"/containers/{native_id}/json")
        if status == 404:
            return None
        if status != 200 or info.get("Id") != native_id:
            raise OwnershipConflictError(
                "recorded child native inspection is unavailable"
            )
        return info

    def stop(self, native_id: str) -> None:
        """Stop the container immediately when it is present."""
        if self.inspect(native_id) is None:
            return
        status, _ = self.request("POST", f"/containers/{native_id}/stop?t=0")
        if status not in {204, 304, 404}:
            raise OwnershipConflictError("recorded child stop is unavailable")


INSPECTION_LIMIT = 1024 * 1024


class HTTPPeer:
    """Pair one socket with the h11 state machine for one HTTP role."""

    def __init__(self, stream: socket.socket, role: type) -> None:
        """Bind the socket and start the protocol state for the role."""
        self.stream = stream
        self.protocol = h11.Connection(role)

    def receive(self) -> h11.Event | type[h11.PAUSED]:
        """Read socket data until the protocol has the next event."""
        while True:
            event = self.protocol.next_event()
            if event is not h11.NEED_DATA:
                return event
            self.protocol.receive_data(self.stream.recv(65536))

    def send(self, event: h11.Event) -> None:
        """Write the bytes of one protocol event to the socket."""
        data = self.protocol.send(event)
        if data:
            self.stream.sendall(data)


def forward_body(source: HTTPPeer, target: HTTPPeer) -> None:
    """Copy body events from the source to the target until the message ends."""
    while True:
        event = source.receive()
        if isinstance(event, h11.ConnectionClosed):
            raise ConnectionError("incomplete Docker message")
        target.send(event)
        if isinstance(event, h11.EndOfMessage):
            return


def inspect_body(
    source: HTTPPeer,
    target: HTTPPeer,
    head: h11.Event,
    transform: Callable[[bytes], tuple[h11.Event, bytes]],
    overflow: Callable[[], None],
) -> None:
    """Inspect bounded carriers; stream oversized carriers without retaining them."""
    body = bytearray()
    while True:
        event = source.receive()
        if isinstance(event, h11.EndOfMessage):
            changed_head, changed_body = transform(bytes(body))
            target.send(changed_head)
            target.send(h11.Data(data=changed_body))
            target.send(h11.EndOfMessage())
            return
        if not isinstance(event, h11.Data):
            raise ConnectionError("incomplete Docker message")
        if len(body) + len(event.data) > INSPECTION_LIMIT:
            overflow()
            target.send(head)
            target.send(h11.Data(data=bytes(body)))
            target.send(event)
            forward_body(source, target)
            return
        body.extend(event.data)


def tunnel(client: HTTPPeer, upstream: HTTPPeer) -> None:
    """Preserve already buffered upgrade bytes and both directions of Docker exec."""
    client.stream.sendall(upstream.protocol.trailing_data[0])
    upstream.stream.sendall(client.protocol.trailing_data[0])
    peers = {client.stream: upstream.stream, upstream.stream: client.stream}
    while peers:
        readable, _, _ = select.select(list(peers), [], [], 1)
        for source in readable:
            data = source.recv(65536)
            if data:
                peers[source].sendall(data)
            else:
                peers[source].shutdown(socket.SHUT_WR)
                del peers[source]
