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
from aptl.core.deployment._cleanup_budget import cleanup_command_timeout
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


def _socket_directory(config: dict[str, object]) -> Path:
    """Return the attempt's recorded socket directory."""
    directory = config.get("socket_directory")
    if not isinstance(directory, str) or not Path(directory).is_absolute():
        raise OwnershipConflictError("recording lifecycle identity changed")
    return Path(directory)


def _publish_config(store: RecordingStore, config: dict[str, object]) -> Path:
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


def existing_sessions(ownership: WorkspaceOwnership) -> tuple[RecordingSession, ...]:
    """Return the recording sessions that the workspace lifecycle state records."""
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
                read_contained_nofollow(ownership.root, relative / name / _CONFIG)
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
    """Control one lab-scoped recorder process through its control socket."""

    store: RecordingStore
    directory: Path
    sockets: dict[str, Path]
    process: subprocess.Popen[bytes] | None = None

    def _control(self, command: str) -> dict[str, object]:
        """Send one control command and return the verified recorder reply."""
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(cleanup_command_timeout(2))
            client.connect(str(self.directory / "control.sock"))
            client.settimeout(cleanup_command_timeout(2))
            client.sendall(_encode({"command": command}))
            client.settimeout(cleanup_command_timeout(2))
            with client.makefile("rb") as stream:
                result = json.loads(stream.readline(1024 * 1024))
            cleanup_command_timeout(2)
        if (
            result.get("workspace_id") != self.store.ownership.workspace_id
            or result.get("attempt_id") != self.store.attempt_id
            or result.get("daemon_id") != self.store.daemon_id
        ):
            raise OwnershipConflictError("recording session identity changed")
        return result

    def status(self) -> dict[str, object] | None:
        """Return the recorder status, or None when no recorder is live."""
        try:
            return self._control("status")
        except FileNotFoundError, ConnectionRefusedError:
            return None
        except (OSError, ValueError) as exc:
            raise OwnershipConflictError("recording status is unavailable") from exc

    def quiesce(self) -> tuple[str, ...]:
        """Drain the recorder and return the gap codes for a failed drain."""
        gaps: list[str] = []
        if not self._drain():
            gaps.append("recording-drain-unavailable")
        return tuple(gaps)

    def _drain(self) -> bool:
        """Ask the recorder to quiesce and return True when it drains in time."""
        deadline = time.monotonic() + cleanup_command_timeout(10)
        try:
            while time.monotonic() < deadline:
                if self._control("quiesce").get("quiesced"):
                    cleanup_command_timeout(10)
                    return True
                time.sleep(cleanup_command_timeout(0.05))
        except OSError, ValueError:
            pass
        return False

    def shutdown(self) -> None:
        """Drain and stop the recorder, and wait for its process to exit."""
        self.quiesce()
        try:
            self._control("shutdown")
        except OSError, ValueError:
            pass
        if self.process is not None:
            try:
                self.process.wait(timeout=cleanup_command_timeout(5))
            except subprocess.TimeoutExpired:
                remaining = cleanup_command_timeout(5)
                self.process.terminate()
                self.process.wait(timeout=remaining)
        cleanup_command_timeout(5)


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
        _require_restart_allowed(store, restart_allowed)
        status = _spawn_recorder(session)
    session.sockets = {key: Path(value) for key, value in status["sockets"].items()}
    return session


def _require_restart_allowed(
    store: RecordingStore, restart_allowed: Callable[[], bool] | None
) -> None:
    """Refuse a restart after issued sockets unless the caller allows it."""
    if store._optional_read(Path("issued.json")) and not (
        restart_allowed is not None and restart_allowed()
    ):
        raise OwnershipConflictError(
            "recording lifecycle was interrupted; stop the lab before another start"
        )


def _spawn_recorder(session: RecordingSession) -> dict[str, object]:
    """Start the recorder process and return its first live status."""
    store = session.store
    config_path = store.ownership.root / store.relative / _CONFIG
    session.process = subprocess.Popen(
        [sys.executable, "-I", "-m", __name__, str(config_path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env={"PATH": os.defpath, "PYTHONNOUSERSITE": "1"},
    )
    status = None
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        status = session.status()
        if status is not None or session.process.poll() is not None:
            break
        time.sleep(0.05)
    if status is None:
        session.shutdown()
        raise OwnershipConflictError("recording process could not start")
    return status


def _serve_control(
    listener: socket.socket,
    session: RecordingSession,
    relay: DockerRecordingRelay,
    supervisor: threading.Thread,
    stopping: threading.Event,
) -> bool:
    """Answer one control command and return True when it asks for shutdown."""
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
    """Run the recorder for one attempt config while it holds the owner lock."""
    config = json.loads(read_contained_nofollow(config_path.parent, _CONFIG))
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
    """Serve the relay and control socket, and return True after a clean stop."""
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
            _control_loop(control, session, relay, supervisor, supervision_stop)
        finally:
            supervision_stop.set()
            control_path.unlink(missing_ok=True)
            supervisor.join(timeout=6)
    return not supervisor.is_alive()


def _control_loop(
    control: socket.socket,
    session: RecordingSession,
    relay: DockerRecordingRelay,
    supervisor: threading.Thread,
    stopping: threading.Event,
) -> None:
    """Answer control commands until one of them asks for shutdown."""
    while True:
        try:
            if _serve_control(control, session, relay, supervisor, stopping):
                return
        except TimeoutError:
            pass
        except OSError, ValueError:
            session.store.gap("recording-control-unavailable")


def _supervise_attempt(inventory: RecordedInventory, stopping: threading.Event) -> None:
    """Enforce child deadlines until stopped, and record a gap on failure."""
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
