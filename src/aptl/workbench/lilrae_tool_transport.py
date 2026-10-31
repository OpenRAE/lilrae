"""Bounded local carrier for an invocation's existing participant tool session."""

from __future__ import annotations

import hmac
import json
import os
from pathlib import Path
import secrets
import socket
from socketserver import StreamRequestHandler, ThreadingUnixStreamServer
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore, Lock, Thread

from aptl.backends.lilrae_participant_tools import (
    LilraeToolSession,
    MAX_CONCURRENT_TOOLS,
    MAX_TOOL_FRAME,
)


def _read(stream) -> dict:
    line = stream.readline(MAX_TOOL_FRAME + 1)
    if not line.endswith(b"\n") or len(line) > MAX_TOOL_FRAME:
        raise ValueError("invalid tool frame")
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ValueError("invalid tool frame")
    return value


def _write(stream, value) -> None:
    data = json.dumps(value, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    if len(data) > MAX_TOOL_FRAME:
        raise ValueError("tool frame limit exceeded")
    stream.write(data)
    stream.flush()


class _Handler(StreamRequestHandler):
    def handle(self) -> None:
        owner = self.server.owner
        call = None
        try:
            self.request.settimeout(owner.timeout)
            value = _read(self.rfile)
            if (
                set(value)
                != {"version", "token", "call_id", "tool", "arguments", "configuration"}
                or type(value["version"]) is not int
                or value["version"] != 1
            ):
                raise ValueError("invalid tool proposal")
            token = value["token"]
            if not isinstance(token, str) or len(token) != 64:
                raise ValueError("invalid tool authority")
            server = next(
                (
                    name
                    for name, expected in owner.tokens.items()
                    if hmac.compare_digest(token, expected)
                ),
                None,
            )
            if server is None:
                raise ValueError("invalid tool authority")
            if not isinstance(value["configuration"], dict):
                raise ValueError("invalid native configuration")
            call = owner.session.begin(
                server,
                value["tool"],
                value["arguments"],
                value["call_id"],
                configuration=value["configuration"],
            )
            # Dispatch is already consumed. Losing this reply is conservative
            # uncertainty, never authority to retry the native action.
            _write(self.wfile, {"accepted": True})
            completion = _read(self.rfile)
            if (
                set(completion) != {"result", "uncertain"}
                or completion["uncertain"] is not False
            ):
                raise ValueError("native outcome is unknown")
            safe = owner.session.complete(call, completion["result"])
            _write(self.wfile, {"accepted": True, "result": safe})
        except Exception:
            if call is not None:
                owner.session.unknown(call)
            try:
                _write(self.wfile, {"accepted": False})
            except Exception:
                pass


class _Server(ThreadingUnixStreamServer):
    """Bound connection threads before starting them, including unauthenticated ones."""

    daemon_threads = False
    block_on_close = True
    request_queue_size = MAX_CONCURRENT_TOOLS

    def __init__(self, path, owner):
        self.owner = owner
        self.capacity = BoundedSemaphore(MAX_CONCURRENT_TOOLS)
        self.guard = Lock()
        self.connections = set()
        super().__init__(path, _Handler)

    def process_request(self, request, client_address):
        if not self.capacity.acquire(blocking=False):
            self.shutdown_request(request)
            return
        with self.guard:
            self.connections.add(request)
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.release(request)
            raise

    def release(self, request):
        with self.guard:
            self.connections.discard(request)
        self.capacity.release()

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.release(request)

    def disconnect(self):
        with self.guard:
            for connection in self.connections:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def handle_error(self, request, client_address):
        # A traceback can include peer payloads. The call remains refused or
        # unknown and the RAES owner retains its settlement obligation.
        pass


class LilraeToolTransport:
    """Private per-invocation IPC, with per-server credentials and no retries."""

    def __init__(self, session: LilraeToolSession) -> None:
        self.session = session
        self.tokens = {
            item.server_id: secrets.token_hex(32) for item in session.bindings
        }
        self.timeout = max(
            item.execution_binding.timeout_seconds for item in session.bindings
        )
        self._directory = None
        self._server = None
        self._thread = None

    def __enter__(self):
        self._directory = TemporaryDirectory(prefix="lilrae-tools-")
        try:
            self.path = str(Path(self._directory.name) / "actions.sock")
            self._server = _Server(self.path, self)
            os.chmod(self.path, 0o600)
            self._thread = Thread(
                target=self._server.serve_forever,
                kwargs={"poll_interval": 0.05},
                daemon=True,
            )
            self._thread.start()
            return self
        except BaseException:
            self.__exit__()
            raise

    def environment(self, server: str) -> dict[str, str]:
        if self._server is None or server not in self.tokens:
            raise ValueError("participant tool server is not bound")
        return {
            "LILRAE_TOOL_SOCKET": self.path,
            "LILRAE_TOOL_TOKEN": self.tokens[server],
            "LILRAE_TOOL_TIMEOUT_MS": str(int(self.timeout * 1000)),
        }

    def __exit__(self, *_):
        if self._server is not None:
            if self._thread is not None and self._thread.is_alive():
                self._server.shutdown()
            self._server.disconnect()
            self._server.server_close()
            self._server = None
        self.session.close()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join()
        if self._directory is not None:
            self._directory.cleanup()
        self.tokens.clear()
