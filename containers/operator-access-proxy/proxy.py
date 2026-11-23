"""Loopback-published TCP relay for declared operator interactive access.

A scenario declares that an operator reaches a node interactively (for example
`agents.red-team-operator.interactive_access.kali-ssh`). The node's own networks
are internal, and Docker never routes host traffic onto an internal network, so
the declared access is unreachable from the operator's host without a relay.

This relay is APTL backend apparatus: one per declared access, attached to the
target's network and to a non-internal access network, published on the host
loopback only. It forwards bytes and does nothing else — no protocol handling,
no credentials — so the target's own SSH daemon (for Kali, the session-capture
broker) still owns authentication and custody (issue #1006).
"""

from __future__ import annotations

import os
import socket
import threading

LISTEN = (
    os.getenv("APTL_PROXY_LISTEN_HOST", "0.0.0.0"),
    int(os.environ["APTL_PROXY_LISTEN_PORT"]),
)
TARGET = (
    os.environ["APTL_PROXY_TARGET_HOST"],
    int(os.environ["APTL_PROXY_TARGET_PORT"]),
)
_CONNECT_TIMEOUT_SECONDS = 10


def _close(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    sock.close()


def _pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        _close(src)
        _close(dst)


def _handle(client: socket.socket) -> None:
    try:
        target = socket.create_connection(TARGET, timeout=_CONNECT_TIMEOUT_SECONDS)
    except OSError:
        _close(client)
        return
    target.settimeout(None)
    threading.Thread(target=_pipe, args=(client, target), daemon=True).start()
    threading.Thread(target=_pipe, args=(target, client), daemon=True).start()


def _udp_request(server: socket.socket, data: bytes, address) -> None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as target:
            target.settimeout(_CONNECT_TIMEOUT_SECONDS)
            target.connect(TARGET)
            target.send(data)
            reply = target.recv(65536)
            server.sendto(reply, address)
    except OSError:
        return


def main() -> None:
    if os.getenv("LILRAE_PROXY_PROTOCOL", "tcp") == "udp":
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
            server.bind(LISTEN)
            while True:
                data, address = server.recvfrom(65536)
                threading.Thread(
                    target=_udp_request, args=(server, data, address), daemon=True
                ).start()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(LISTEN)
        server.listen()
        while True:
            client, _addr = server.accept()
            _handle(client)


if __name__ == "__main__":
    main()
