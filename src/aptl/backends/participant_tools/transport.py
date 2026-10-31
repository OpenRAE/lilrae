"""Bounded local carrier for an invocation's existing participant tool session."""

from __future__ import annotations

import hmac
import json
import os
from pathlib import Path
import secrets
import socket
from socketserver import StreamRequestHandler, ThreadingTCPServer
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore, Lock, Thread
from typing import Annotated, BinaryIO
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from aptl.core.participant_tools.contracts import (
    ToolSession,
    MAX_CONCURRENT_TOOLS,
    MAX_TOOL_FRAME,
)


class _Frame(BaseModel):
    """Strict wire object with no extension fields."""

    model_config = ConfigDict(extra="forbid", strict=True)


class _Proposal(_Frame):
    """One complete native call and its installed server authority."""

    version: Annotated[int, Field(ge=1, le=1)]
    token: str
    call_id: str
    tool: str
    arguments: dict[str, JsonValue]
    configuration: dict[str, JsonValue]


class _Completion(_Frame):
    """Native result with an explicit uncertainty signal."""

    result: dict[str, JsonValue]
    uncertain: Annotated[bool, Field(strict=True)]


def _read(stream: BinaryIO) -> bytes:
    """Read one size-limited newline-terminated frame."""
    line = stream.readline(MAX_TOOL_FRAME + 1)
    if not line.endswith(b"\n") or len(line) > MAX_TOOL_FRAME:
        raise ValueError("invalid tool frame")
    return line


def _write(stream: BinaryIO, value: dict[str, object]) -> None:
    """Write and flush one size-limited JSON frame."""
    data = json.dumps(value, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    if len(data) > MAX_TOOL_FRAME:
        raise ValueError("tool frame limit exceeded")
    stream.write(data)
    stream.flush()


class _Handler(StreamRequestHandler):
    """Authenticate one proposal and report its terminal or unknown outcome."""

    def handle(self) -> None:
        owner = self.server.owner
        call = None
        try:
            self.request.settimeout(owner.timeout)
            proposal = _Proposal.model_validate_json(_read(self.rfile))
            token = proposal.token
            if len(token) != 64:
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
            call = owner.session.begin(
                server,
                proposal.tool,
                proposal.arguments,
                proposal.call_id,
                configuration=proposal.configuration,
            )
            # Dispatch is already consumed. Losing this reply is conservative
            # uncertainty, never authority to retry the native action.
            _write(self.wfile, {"accepted": True})
            completion = _Completion.model_validate_json(_read(self.rfile))
            if completion.uncertain:
                raise ValueError("native outcome is unknown")
            safe = owner.session.complete(call, completion.result)
            _write(self.wfile, {"accepted": True, "result": safe})
        except Exception:
            if call is not None:
                owner.session.unknown(call)
            try:
                _write(self.wfile, {"accepted": False})
            except Exception:
                pass


class _Server(ThreadingTCPServer):
    """Bound connection threads before starting them, including unauthenticated ones."""

    daemon_threads = False
    block_on_close = True
    request_queue_size = MAX_CONCURRENT_TOOLS

    def __init__(self, path: str, owner: LilraeToolTransport) -> None:
        # UnixStreamServer uses this same base and address-family override,
        # but the stdlib does not export that class on Windows.
        self.address_family = socket.AF_UNIX
        self.owner = owner
        self.capacity = BoundedSemaphore(MAX_CONCURRENT_TOOLS)
        self.guard = Lock()
        self.connections = set()
        super().__init__(path, _Handler)

    def process_request(self, request: socket.socket, client_address: str) -> None:
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

    def release(self, request: socket.socket) -> None:
        with self.guard:
            self.connections.discard(request)
        self.capacity.release()

    def process_request_thread(
        self, request: socket.socket, client_address: str
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.release(request)

    def disconnect(self) -> None:
        with self.guard:
            for connection in self.connections:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def handle_error(self, request: socket.socket, client_address: str) -> None:
        # A traceback can include peer payloads. The call remains refused or
        # unknown and the RAES owner retains its settlement obligation.
        pass


class LilraeToolTransport:
    """Private per-invocation IPC, with per-server credentials and no retries."""

    def __init__(self, session: ToolSession) -> None:
        if os.name != "posix":
            raise ValueError("participant tool transport requires POSIX")
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

    def __enter__(self) -> LilraeToolTransport:
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

    def __exit__(self, *_: object) -> None:
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
