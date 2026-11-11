"""Attempt-owned Unix socket recording, with unchanged upstream Docker authority."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import selectors
import socket
import stat
import threading
import time
from typing import Self
from uuid import uuid4

import h11

from aptl.core.deployment._compose_resource_ownership import OwnershipConflictError
from aptl.core.deployment._docker_endpoint_binding import _local_docker_socket_identity
from aptl.core.deployment.lilrae_docker_recording import (
    CreationIntent,
    RecordedCreation,
    RecordingStore,
)
from aptl.core.deployment.lilrae_docker_http import (
    HTTPPeer,
    forward_body,
    inspect_body,
    tunnel,
)
from aptl.utils.pathsafe import open_private_dir_contained_nofollow

_CREATE = re.compile(rb"/(?:v\d+\.\d+/)?containers/create(?:\?|$)")
_OPAQUE_ALLOCATION = re.compile(
    rb"/(?:v\d+\.\d+/)?(?:build|services/create|networks/create|volumes/create|plugins/.*)(?:\?|$)"
)
_CANONICAL_SOCKETS = frozenset({"/var/run/docker.sock", "/run/docker.sock"})
_BYPASS_SOURCES = frozenset({"/", "/run", "/var", "/var/run"})
_CREATE_REJECTED = frozenset({400, 401, 403, 404, 405, 409, 422})


def _discard_creation(_creation: RecordedCreation) -> None:
    """Ignore a recorded creation when no observer is set."""


def _request_path(request: h11.Request) -> bytes:
    """Return the request target without the query string."""
    return request.target.split(b"?", 1)[0]


def _must_close(client: HTTPPeer, upstream: HTTPPeer) -> bool:
    """Return True when one of the two HTTP peers must close the connection."""
    return h11.MUST_CLOSE in {
        client.protocol.our_state,
        client.protocol.their_state,
        upstream.protocol.our_state,
        upstream.protocol.their_state,
    }


@dataclass
class _Holder:
    """Keep the causal source and parent identity for one recording endpoint."""

    source_address: str
    timeout_seconds: int
    native_id: str = ""
    ready: threading.Event = field(default_factory=threading.Event)


class DockerRecordingRelay:
    """One bounded connection owner, with distinct causal endpoints per holder."""

    def __init__(self, store: RecordingStore, upstream: Path, directory: Path) -> None:
        self.store = store
        self.upstream = upstream
        self.directory = directory
        self.identity = _local_docker_socket_identity(str(upstream))
        if self.identity is None:
            raise OwnershipConflictError("recording upstream socket is unavailable")
        self._selector = selectors.DefaultSelector()
        self._guard = threading.RLock()
        self._stopping = threading.Event()
        self._quiescing = threading.Event()
        self._capacity = threading.BoundedSemaphore(64)
        self._streams: set[socket.socket] = set()
        self._threads: set[threading.Thread] = set()
        self._listeners: list[socket.socket] = []
        self._paths: set[str] = set()
        self._roots: dict[str, Path] = {}
        self._worker: threading.Thread | None = None
        self._inflight = 0
        self.on_creation: Callable[[RecordedCreation], None] = _discard_creation

    def __enter__(self) -> Self:
        """Start the accept worker and return the relay."""
        self._worker = threading.Thread(
            target=self._accept, name="lilrae-docker-recording", daemon=True
        )
        self._worker.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        """Close the relay."""
        self.close()

    def endpoint(self, source_address: str, *, timeout_seconds: int) -> Path:
        """Return the recording endpoint for a source, and open it on first use."""
        with self._guard:
            if source_address not in self._roots:
                holder = _Holder(source_address, timeout_seconds)
                holder.ready.set()
                self._roots[source_address] = self._listen(holder)
            return self._roots[source_address]

    def _listen(self, holder: _Holder) -> Path:
        """Open a new recording socket for a holder and return its path."""
        if len(self._listeners) >= 1024:
            raise ValueError("Docker recording endpoint capacity reached")
        descriptor = open_private_dir_contained_nofollow(
            self.directory.parent, Path(self.directory.name)
        )
        os.close(descriptor)
        path = self.directory / f"{uuid4().hex}.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(str(path))
            upstream_mode = self.upstream.stat()
            os.chmod(path, stat.S_IMODE(upstream_mode.st_mode))
            os.chown(path, -1, upstream_mode.st_gid)
            listener.listen(64)
            listener.setblocking(False)
            self._selector.register(listener, selectors.EVENT_READ, holder)
            self._listeners.append(listener)
            self._paths.add(str(path))
        except BaseException:
            listener.close()
            path.unlink(missing_ok=True)
            raise
        return path

    def _accept(self) -> None:
        """Accept connections and start one serving thread for each connection."""
        while not self._stopping.is_set():
            for key, _ in self._selector.select(timeout=0.1):
                with self._guard:
                    stream, _ = key.fileobj.accept()
                    stream.setblocking(True)
                    if self._quiescing.is_set():
                        stream.close()
                        continue
                    if not self._capacity.acquire(blocking=False):
                        self.store.gap("connection-capacity")
                        stream.close()
                        continue
                    self._streams.add(stream)
                    worker = threading.Thread(
                        target=self._serve, args=(stream, key.data), daemon=True
                    )
                    self._threads.add(worker)
                    worker.start()

    def _serve(self, stream: socket.socket, holder: _Holder) -> None:
        """Connect one client stream to the upstream Docker socket and relay it."""
        upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        with self._guard:
            self._streams.add(upstream)
        try:
            if not holder.ready.wait(10):
                raise OwnershipConflictError("recorded delegation is unavailable")
            if _local_docker_socket_identity(str(self.upstream)) != self.identity:
                raise OwnershipConflictError("recording upstream socket changed")
            upstream.settimeout(10)
            upstream.connect(str(self.upstream))
            upstream.settimeout(None)
            self._exchange(
                HTTPPeer(stream, h11.SERVER), HTTPPeer(upstream, h11.CLIENT), holder
            )
        except OSError, ValueError, h11.ProtocolError, OwnershipConflictError:
            # Lost create responses remain durable pending intents. Cancellation
            # of an ordinary stream does not erase already-recorded identities.
            pass
        finally:
            stream.close()
            upstream.close()
            with self._guard:
                self._streams.discard(stream)
                self._streams.discard(upstream)
                self._threads.discard(threading.current_thread())
            self._capacity.release()

    def _exchange(self, client: HTTPPeer, upstream: HTTPPeer, holder: _Holder) -> None:
        """Relay request and response cycles until one side stops the connection."""
        while not self._stopping.is_set() and self._cycle(client, upstream, holder):
            client.protocol.start_next_cycle()
            upstream.protocol.start_next_cycle()

    def _cycle(self, client: HTTPPeer, upstream: HTTPPeer, holder: _Holder) -> bool:
        """Relay one request cycle and return True when the connection continues."""
        request = client.receive()
        if isinstance(request, h11.ConnectionClosed):
            return False
        if not isinstance(request, h11.Request):
            raise ValueError("invalid Docker request framing")
        if self._quiescing.is_set() or self._transaction(
            client, upstream, holder, request
        ):
            return False
        return not _must_close(client, upstream)

    def _transaction(
        self,
        client: HTTPPeer,
        upstream: HTTPPeer,
        holder: _Holder,
        request: h11.Request,
    ) -> bool:
        """Relay one request and record container creation when it applies."""
        if client.protocol.they_are_waiting_for_100_continue:
            client.send(h11.InformationalResponse(status_code=100, headers=[]))
            request = h11.Request(
                method=request.method,
                target=request.target,
                headers=[
                    (key, value) for key, value in request.headers if key != b"expect"
                ],
            )
        if request.method != b"POST" or not _CREATE.fullmatch(_request_path(request)):
            if request.method == b"POST" and _OPAQUE_ALLOCATION.fullmatch(
                _request_path(request)
            ):
                self.store.gap("opaque-native-allocation")
            upstream.send(request)
            forward_body(client, upstream)
            return self._response(client, upstream, None, None)
        with self._guard:
            if self._quiescing.is_set():
                return True
            self._inflight += 1
        try:
            intent = self.store.begin(
                holder.source_address,
                parent_native_id=holder.native_id,
                timeout_seconds=holder.timeout_seconds,
            )
            delegated = _Holder(holder.source_address, holder.timeout_seconds)
            self._forward_create(client, upstream, request, delegated)
            return self._response(client, upstream, intent, delegated)
        finally:
            with self._guard:
                self._inflight -= 1

    def _forward_create(
        self,
        client: HTTPPeer,
        upstream: HTTPPeer,
        request: h11.Request,
        delegated: _Holder,
    ) -> None:
        """Relay a create request body with socket delegation rewritten."""

        def transform(body: bytes) -> tuple[h11.Request, bytes]:
            """Rewrite socket delegation in the create body, or keep the body."""
            try:
                document = json.loads(body)
                self._rewrite_delegation(document, delegated)
                rewritten = json.dumps(document, separators=(",", ":")).encode()
            except TypeError, ValueError, AttributeError:
                self.store.gap("create-request-uninspected")
                return request, body
            headers = [
                (key, value)
                for key, value in request.headers
                if key not in {b"content-length", b"transfer-encoding", b"expect"}
            ]
            headers.append((b"content-length", str(len(rewritten)).encode()))
            return h11.Request(
                method=request.method, target=request.target, headers=headers
            ), rewritten

        inspect_body(
            client,
            upstream,
            request,
            transform,
            lambda: self.store.gap("create-request-uninspected"),
        )

    def _rewrite_delegation(
        self, document: dict[str, object], delegated: _Holder
    ) -> None:
        """Point Docker socket mounts in a create body at a delegated endpoint."""
        endpoint: Path | None = None

        def delegation_path() -> Path:
            """Open the delegated endpoint once and return its path."""
            nonlocal endpoint
            if endpoint is None:
                with self._guard:
                    endpoint = self._listen(delegated)
            return endpoint

        host = document.get("HostConfig") or {}
        self._rewrite_binds(host.get("Binds") or [], delegation_path)
        self._rewrite_mounts(host.get("Mounts") or [], delegation_path)
        if host.get("VolumesFrom"):
            self.store.gap("inherited-socket-delegation")
        if any(
            str(item).startswith(("DOCKER_HOST=", "DOCKER_CONTEXT="))
            for item in document.get("Env") or []
        ):
            self.store.gap("alternate-docker-endpoint")

    def _rewrite_binds(
        self, binds: list[str], delegation_path: Callable[[], Path]
    ) -> None:
        """Replace Docker socket bind sources with the delegated endpoint."""
        for index, binding in enumerate(binds):
            source, separator, rest = binding.partition(":")
            if os.path.normpath(source) in _CANONICAL_SOCKETS or source in self._paths:
                binds[index] = f"{delegation_path()}{separator}{rest}"
            elif source in _BYPASS_SOURCES:
                self.store.gap("possible-socket-bypass")

    def _rewrite_mounts(
        self, mounts: list[dict[str, object]], delegation_path: Callable[[], Path]
    ) -> None:
        """Replace Docker socket bind mount sources with the delegated endpoint."""
        for mount in mounts:
            if mount.get("Type") == "bind" and mount.get("Source") in (
                _CANONICAL_SOCKETS | self._paths
            ):
                mount["Source"] = str(delegation_path())

    def _response(
        self,
        client: HTTPPeer,
        upstream: HTTPPeer,
        intent: CreationIntent | None,
        delegated: _Holder | None,
    ) -> bool:
        """Relay one Docker response and return True when the stream is done."""
        response = self._final_response(client, upstream)
        if response is None:
            return True
        if intent is None or delegated is None:
            client.send(response)
            forward_body(upstream, client)
        else:

            def transform(body: bytes) -> tuple[h11.Response, bytes]:
                """Record the create outcome and keep the response unchanged."""
                self._record_outcome(response, body, intent, delegated)
                return response, body

            inspect_body(
                upstream,
                client,
                response,
                transform,
                lambda: self.store.gap("creation-response-unrecorded"),
            )
        return False

    @staticmethod
    def _final_response(client: HTTPPeer, upstream: HTTPPeer) -> h11.Response | None:
        """Relay interim responses and return the final one, or None after an upgrade."""
        response = upstream.receive()
        while isinstance(response, h11.InformationalResponse):
            client.send(response)
            if response.status_code == 101:
                tunnel(client, upstream)
                return None
            response = upstream.receive()
        if not isinstance(response, h11.Response):
            raise ConnectionError("Docker response is unavailable")
        return response

    def _record_outcome(
        self,
        response: h11.Response,
        body: bytes,
        intent: CreationIntent,
        delegated: _Holder,
    ) -> None:
        """Record a create response as a creation, a failure, or a gap."""
        if response.status_code == 201:
            self._record_creation(body, intent, delegated)
        elif response.status_code in _CREATE_REJECTED:
            self.store.failed(intent)
        else:
            self.store.gap("creation-response-unrecorded")

    def _record_creation(
        self, body: bytes, intent: CreationIntent, delegated: _Holder
    ) -> None:
        """Commit the created container ID and tell the creation observer."""
        try:
            creation = self.store.commit(intent, json.loads(body)["Id"])
            delegated.native_id = creation.native_id
            delegated.ready.set()
        except (
            ValueError,
            TypeError,
            KeyError,
            OwnershipConflictError,
            OSError,
        ):
            self.store.gap("creation-response-unrecorded")
            return
        try:
            self.on_creation(creation)
        except OSError, ValueError, OwnershipConflictError:
            # The ID is durable; live inventory discloses any
            # unavailable metadata without losing that identity.
            pass

    def quiesce(self) -> bool:
        """Stop new create requests and return True when none are in flight."""
        with self._guard:
            self._quiescing.set()
            return self._inflight == 0

    def close(self) -> None:
        """Stop the relay, close all sockets, and wait for the workers."""
        self._stopping.set()
        if self._worker:
            self._worker.join(2)
        with self._guard:
            for stream in self._streams:
                try:
                    stream.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            for listener in self._listeners:
                path = Path(listener.getsockname())
                self._selector.unregister(listener)
                listener.close()
                path.unlink(missing_ok=True)
            workers = tuple(self._threads)
        deadline = time.monotonic() + 2
        for worker in workers:
            worker.join(max(0, deadline - time.monotonic()))
        self._selector.close()
