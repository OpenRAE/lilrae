"""Lab-scoped recorder lifecycle. No daemon installation or network listener."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable

try:
    import fcntl
except ModuleNotFoundError:
    fcntl = None
import contextlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

from aptl.core.deployment._compose_resource_ownership import (
    OwnershipConflictError,
    WorkspaceOwnership,
)
from aptl.core.deployment.lilrae_docker_http import NativeDocker
from aptl.core.deployment.lilrae_docker_recording import RecordingStore, _encode
from aptl.core.deployment.lilrae_docker_relay import DockerRecordingRelay
from aptl.core.deployment.lilrae_recorded_inventory import RecordedInventory
from aptl.utils.pathsafe import (
    PathContainmentError,
    open_private_dir_contained_nofollow,
    read_contained_nofollow,
    listdir_contained_nofollow,
    REASON_NOT_FOUND,
    replace_private_nofollow,
)


_CONFIG = Path("config.json")


def _socket_directory(config: dict) -> Path:
    """Return the attempt's recorded socket directory."""
    directory = config.get("socket_directory")
    if not isinstance(directory, str) or not Path(directory).is_absolute():
        raise OwnershipConflictError("recording lifecycle identity changed")
    return Path(directory)


def _publish_config(store: RecordingStore, config: dict) -> Path:
    """Publish the write-once attempt config with its private socket directory.

    The first start creates an unpredictable owner-only directory, because a
    fixed name in a shared temporary directory lets another local user occupy
    it first. Later starts reuse the recorded directory.
    """
    prior = store._optional_read(_CONFIG)
    if prior is not None:
        directory = _socket_directory(prior)
        store._publish(_CONFIG, {**config, "socket_directory": str(directory)})
        return directory
    directory = Path(tempfile.mkdtemp(prefix="lilrae-recording-"))
    try:
        store._publish(_CONFIG, {**config, "socket_directory": str(directory)})
    except BaseException:
        directory.rmdir()
        raise
    return directory


def existing_sessions(ownership: WorkspaceOwnership) -> tuple["RecordingSession", ...]:
    relative = Path(".aptl/lifecycle/lilrae-docker-recording-v1")
    try:
        names = listdir_contained_nofollow(ownership.root, relative)
    except FileNotFoundError:
        return ()
    except PathContainmentError as exc:
        if exc.reason == REASON_NOT_FOUND:
            return ()
        raise OwnershipConflictError(
            "recording lifecycle state is unavailable"
        ) from exc
    sessions = []
    for name in names:
        try:
            config = json.loads(
                read_contained_nofollow(ownership.root, relative / name / "config.json")
            )
        except FileNotFoundError:
            continue
        except PathContainmentError as exc:
            if exc.reason == REASON_NOT_FOUND:
                continue
            raise
        store = RecordingStore(
            ownership, daemon_id=config["daemon_id"], attempt_id=config["attempt_id"]
        )
        if store.relative.name != name or config["root"] != str(ownership.root):
            raise OwnershipConflictError("recording lifecycle identity changed")
        sessions.append(RecordingSession(store, _socket_directory(config), {}))
    return tuple(sessions)


@dataclass
class RecordingSession:
    store: RecordingStore
    directory: Path
    sockets: dict[str, Path]
    process: subprocess.Popen | None = None

    def _control(self, command: str) -> dict:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(str(self.directory / "control.sock"))
            client.sendall(_encode({"command": command}))
            with client.makefile("rb") as stream:
                result = json.loads(stream.readline(1024 * 1024))
        if (
            result.get("workspace_id") != self.store.ownership.workspace_id
            or result.get("attempt_id") != self.store.attempt_id
            or result.get("daemon_id") != self.store.daemon_id
        ):
            raise OwnershipConflictError("recording session identity changed")
        return result

    def status(self) -> dict | None:
        try:
            return self._control("status")
        except FileNotFoundError, ConnectionRefusedError:
            return None
        except (OSError, ValueError) as exc:
            raise OwnershipConflictError("recording status is unavailable") from exc

    def quiesce(self) -> tuple[str, ...]:
        deadline = time.monotonic() + 10
        try:
            while time.monotonic() < deadline:
                if self._control("quiesce").get("quiesced"):
                    return ()
                time.sleep(0.05)
        except OSError, ValueError:
            pass
        return ("recording-drain-unavailable",)

    def shutdown(self) -> None:
        self.quiesce()
        try:
            self._control("shutdown")
        except OSError, ValueError:
            pass
        if self.process is not None:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=5)


def start_recording(
    store: RecordingStore,
    upstream: Path,
    authorities: dict[str, int],
    *,
    restart_allowed: Callable[[], bool] | None = None,
) -> RecordingSession:
    """Start only an admitted lab's process, or reuse its currently live owner."""
    if fcntl is None:
        raise OwnershipConflictError(
            "Docker recording requires Unix lifecycle ownership"
        )
    config = {
        "root": str(store.ownership.root),
        "project": store.ownership.logical_project_name,
        "attempt_id": store.attempt_id,
        "daemon_id": store.daemon_id,
        "upstream": str(upstream),
        "authorities": authorities,
    }
    directory = _publish_config(store, config)
    session = RecordingSession(store, directory, {})
    status = session.status()
    if status is None:
        if store._optional_read(Path("issued.json")) and not (
            restart_allowed is not None and restart_allowed()
        ):
            raise OwnershipConflictError(
                "recording lifecycle was interrupted; stop the lab before another start"
            )
        config_path = store.ownership.root / store.relative / _CONFIG
        session.process = subprocess.Popen(
            [sys.executable, "-I", "-m", __name__, str(config_path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env={"PATH": os.defpath, "PYTHONNOUSERSITE": "1"},
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status = session.status()
            if status is not None:
                break
            if session.process.poll() is not None:
                break
            time.sleep(0.05)
        if status is None:
            session.shutdown()
            raise OwnershipConflictError("recording process could not start")
    session.sockets = {key: Path(value) for key, value in status["sockets"].items()}
    return session


def _serve_control(
    listener: socket.socket,
    session: RecordingSession,
    relay: DockerRecordingRelay,
    supervisor: threading.Thread,
    stopping: threading.Event,
) -> bool:
    client, _ = listener.accept()
    with client:
        client.settimeout(2)
        with client.makefile("rb") as stream:
            command = json.loads(stream.readline(1024)).get("command")
        result = {
            "workspace_id": session.store.ownership.workspace_id,
            "attempt_id": session.store.attempt_id,
            "daemon_id": session.store.daemon_id,
            "sockets": {key: str(value) for key, value in session.sockets.items()},
            "deadline_supervision": supervisor.is_alive(),
        }
        if command in {"quiesce", "shutdown"}:
            stopping.set()
            result["quiesced"] = relay.quiesce() and not supervisor.is_alive()
        client.sendall(_encode(result))
    return command == "shutdown"


def serve_recording(config_path: Path) -> None:
    config = json.loads(read_contained_nofollow(config_path.parent, "config.json"))
    ownership = WorkspaceOwnership.load(Path(config["root"]), config["project"])
    if ownership is None:
        raise OwnershipConflictError("recording workspace is unavailable")
    store = RecordingStore(
        ownership, daemon_id=config["daemon_id"], attempt_id=config["attempt_id"]
    )
    if ownership.root / store.relative / _CONFIG != config_path:
        raise OwnershipConflictError("recording configuration identity changed")
    directory = _socket_directory(config)
    # Fails closed unless this user owns the directory and only it has access.
    os.close(
        open_private_dir_contained_nofollow(directory.parent, Path(directory.name))
    )
    state = open_private_dir_contained_nofollow(ownership.root, store.relative)
    try:
        lock = os.open(
            "owner.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=state
        )
    finally:
        os.close(state)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        replace_private_nofollow(
            ownership.root, store.relative / "closed.json", _encode({"closed": False})
        )
        if _serve_owned(
            store, Path(config["upstream"]), directory, config["authorities"]
        ):
            replace_private_nofollow(
                ownership.root,
                store.relative / "closed.json",
                _encode({"closed": True}),
            )
            # A residual empty owner-only directory is harmless.
            with contextlib.suppress(OSError):
                directory.rmdir()
    finally:
        os.close(lock)


def _serve_owned(
    store: RecordingStore, upstream: Path, directory: Path, authorities: dict[str, int]
) -> bool:
    native = NativeDocker(upstream, store.daemon_id)
    native.verify_daemon()
    inventory = RecordedInventory(store, native)
    control_path = directory / "control.sock"
    control_path.unlink(missing_ok=True)
    with (
        DockerRecordingRelay(store, upstream, directory) as relay,
        socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as control,
    ):
        relay.on_creation = inventory.capture
        sockets = {
            source: relay.endpoint(source, timeout_seconds=timeout)
            for source, timeout in authorities.items()
        }
        session = RecordingSession(store, directory, sockets)
        control.bind(str(control_path))
        os.chmod(control_path, 0o600)
        control.listen(4)
        control.settimeout(0.2)
        store._publish(Path("issued.json"), {"issued": True})
        supervision_stop = threading.Event()
        supervisor = threading.Thread(
            target=_supervise_attempt,
            args=(inventory, supervision_stop),
            name="lilrae-child-deadlines",
            daemon=True,
        )
        supervisor.start()
        try:
            while True:
                try:
                    if _serve_control(
                        control, session, relay, supervisor, supervision_stop
                    ):
                        break
                except TimeoutError:
                    pass
                except OSError, ValueError:
                    store.gap("recording-control-unavailable")
        finally:
            supervision_stop.set()
            control_path.unlink(missing_ok=True)
            supervisor.join(timeout=6)
    return not supervisor.is_alive()


def _supervise_attempt(inventory: RecordedInventory, stopping: threading.Event) -> None:
    try:
        while not stopping.wait(0.5):
            if inventory.supervise(cancelled=stopping.is_set):
                inventory.store.gap("deadline-supervision-unavailable")
    except OSError, ValueError, OwnershipConflictError, PathContainmentError:
        inventory.store.gap("deadline-supervision-unavailable")


if __name__ == "__main__":
    try:
        serve_recording(Path(sys.argv[1]))
    except OSError, ValueError, OwnershipConflictError, PathContainmentError:
        raise SystemExit(1) from None
