"""The lab owns its recorder process and can drain it without PID guessing."""

import json
import os
from pathlib import Path
import yaml
import threading
import time
import pytest

from tests.test_lilrae_docker_recording import _store
from tests.test_lilrae_docker_recording_transport import call, fake_docker


@pytest.mark.parametrize("package", [False, True])
def test_recorder_ignores_project_local_python_shadowing(
    tmp_path, monkeypatch, package
):
    from aptl.core.deployment.lilrae_docker_recorder import start_recording

    project = tmp_path / "untrusted-project"
    project.mkdir()
    marker = tmp_path / "shadow-was-imported"
    shadow = project / "aptl.py"
    if package:
        (project / "aptl").mkdir()
        shadow = project / "aptl" / "__init__.py"
    shadow.write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
        "raise RuntimeError('untrusted project package')\n"
    )
    monkeypatch.chdir(project)
    store = _store(tmp_path)
    with fake_docker() as (upstream, _endpoints, _calls):
        session = start_recording(store, upstream, {"provision.node.holder": 60})
        try:
            assert session.status() is not None
            assert not marker.exists()
        finally:
            session.shutdown()


def test_backend_wires_its_own_recorder_before_the_holder_is_started(tmp_path):
    from aptl.core.deployment.docker_compose import DockerComposeBackend
    from aptl.core.deployment._docker_endpoint_binding import (
        _local_docker_socket_identity,
    )
    from tests.test_raes_runtime_orchestration import _spec

    store = _store(tmp_path)
    backend = DockerComposeBackend(tmp_path)
    backend._resource_ownership = store.ownership
    backend._resource_attempt_id = store.attempt_id
    backend._docker_daemon_id = store.daemon_id
    with fake_docker() as (upstream, _endpoints, _calls):
        backend._docker_socket_path = str(upstream)
        backend._docker_socket_identity = _local_docker_socket_identity(str(upstream))
        assert backend._prepare_docker_recording(_spec()) is None
        try:
            override = backend._write_docker_recording_override(_spec())
            source = yaml.safe_load(override.read_text())["services"]["orborus"][
                "volumes"
            ][0]["source"]
            assert source != str(upstream)
            assert Path(source).is_socket()
            assert (
                call(source, "POST", "/v1.44/containers/create", {"Image": "example"})[
                    0
                ]
                == 201
            )
            inventory = backend.runtime_descendant_inventory(store.attempt_id)
            assert inventory.complete
            assert len(inventory.children) == 1
            assert (
                call(source, "POST", "/v1.44/services/create", {"Name": "service"})[0]
                == 200
            )
            assert backend._quiesce_docker_recordings()
        finally:
            backend._recording_session.shutdown()


def test_recorder_process_is_scoped_reused_and_stopped_with_the_lab(tmp_path):
    from aptl.core.deployment.lilrae_docker_recorder import start_recording

    store = _store(tmp_path)
    with fake_docker() as (upstream, _endpoints, _calls):
        session = start_recording(store, upstream, {"provision.node.holder": 60})
        try:
            again = start_recording(store, upstream, {"provision.node.holder": 60})
            assert again.sockets == session.sockets
            status, body = call(
                session.sockets["provision.node.holder"],
                "POST",
                "/v1.44/containers/create",
                {"Image": "identical-image"},
            )
            assert status == 201
            native_id = json.loads(body)["Id"]
            assert store.creation(native_id).attempt_id == store.attempt_id
            assert session.quiesce() == ()
        finally:
            session.shutdown()
        assert session.status() is None
        assert session.process.poll() is not None


def test_control_remains_responsive_while_native_deadline_inspection_stalls(tmp_path):
    from aptl.core.deployment.lilrae_docker_recorder import start_recording

    gate = threading.Event()
    supervision_entered = threading.Event()
    store = _store(tmp_path)
    results = []
    with fake_docker(inspection_gate=gate, supervision_entered=supervision_entered) as (
        upstream,
        _endpoints,
        _calls,
    ):
        session = start_recording(store, upstream, {"provision.node.holder": 1})
        creator = threading.Thread(
            target=lambda: results.append(
                call(
                    session.sockets["provision.node.holder"],
                    "POST",
                    "/v1.44/containers/create",
                    {"Image": "example"},
                    timeout=10,
                )
            ),
            daemon=True,
        )
        try:
            creator.start()
            deadline = time.monotonic() + 2
            while not store.records() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert store.records()
            assert supervision_entered.wait(3)
            assert session.status() is not None
        finally:
            gate.set()
            creator.join(4)
            session.shutdown()


def test_child_deadline_is_enforced_while_the_parent_start_owns_the_project(tmp_path):
    from aptl.core.deployment.lilrae_docker_recorder import start_recording
    from aptl.core.lifecycle_guard import lifecycle_mutation_lock

    store = _store(tmp_path)
    with fake_docker() as (upstream, _endpoints, _calls):
        with lifecycle_mutation_lock(tmp_path):
            session = start_recording(store, upstream, {"provision.node.holder": 1})
            try:
                endpoint = session.sockets["provision.node.holder"]
                _, body = call(
                    endpoint, "POST", "/v1.44/containers/create", {"Image": "example"}
                )
                native_id = json.loads(body)["Id"]
                call(endpoint, "POST", f"/containers/{native_id}/start")
                deadline = time.monotonic() + 3
                running = True
                while running and time.monotonic() < deadline:
                    _, body = call(upstream, "GET", f"/containers/{native_id}/json")
                    running = json.loads(body)["State"]["Running"]
                    if running:
                        time.sleep(0.05)
                assert not running
            finally:
                session.shutdown()


def test_a_clean_retry_requires_parent_cleanup_proof_and_gets_new_socket_inodes(
    tmp_path,
):
    from aptl.core.deployment.lilrae_docker_recorder import start_recording
    from aptl.core.deployment._compose_resource_ownership import OwnershipConflictError

    store = _store(tmp_path)
    with fake_docker() as (upstream, _endpoints, _calls):
        first = start_recording(store, upstream, {"provision.node.holder": 60})
        old_socket = first.sockets["provision.node.holder"]
        first.shutdown()
        with pytest.raises(OwnershipConflictError):
            start_recording(store, upstream, {"provision.node.holder": 60})
        second = start_recording(
            store, upstream, {"provision.node.holder": 60}, restart_allowed=lambda: True
        )
        try:
            assert second.sockets["provision.node.holder"] != old_socket
            assert not old_socket.exists()
            assert second.store.attempt_id == first.store.attempt_id
        finally:
            second.shutdown()


def test_recorder_sockets_live_in_an_unpredictable_owner_only_directory(tmp_path):
    import stat

    from aptl.core.deployment.lilrae_docker_recorder import start_recording

    first, second = _store(tmp_path / "first"), _store(tmp_path / "second")
    with fake_docker() as (upstream, _endpoints, _calls):
        sessions = [
            start_recording(store, upstream, {"provision.node.holder": 60})
            for store in (first, second)
        ]
        try:
            directories = [session.directory for session in sessions]
            assert directories[0] != directories[1]
            for directory in directories:
                mode = directory.lstat()
                assert stat.S_ISDIR(mode.st_mode)
                assert mode.st_uid == os.getuid()
                assert stat.S_IMODE(mode.st_mode) & 0o077 == 0
            assert first._read(Path("config.json"))["socket_directory"] == str(
                directories[0]
            )
        finally:
            for session in sessions:
                session.shutdown()
    assert not any(directory.exists() for directory in directories)
