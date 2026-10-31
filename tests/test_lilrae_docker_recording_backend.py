"""Recorder wiring and child cleanup use the existing deployment owner."""

import json
import subprocess

import pytest

from aptl.core.deployment._compose_resource_ownership import OwnershipConflictError
from aptl.core.deployment._compose_runtime_orchestration import (
    effective_orchestration_model_errors,
)
from aptl.core.deployment.docker_compose import DockerComposeBackend
from tests.test_lilrae_docker_recording import _store
from tests.test_lilrae_docker_recording_lifecycle import Native
from tests.test_raes_runtime_orchestration import _spec
from aptl.core.deployment.runtime_materialization import (
    SHARED_DOCKER_PROFILE,
    effective_runtime_contract_issues,
)


def test_effective_model_accepts_only_the_exact_trusted_recording_source():
    spec = _spec()
    source = "/tmp/lilrae-recording-1000/test/root.sock"
    payload = {
        "services": {
            "orborus": {
                "volumes": [
                    {
                        "type": "bind",
                        "source": source,
                        "target": "/var/run/docker.sock",
                        "read_only": False,
                    }
                ]
            }
        }
    }
    assert effective_orchestration_model_errors(payload, spec)
    assert not effective_orchestration_model_errors(
        payload, spec, recording_sockets={"provision.node.orborus": source}
    )
    payload["services"]["orborus"]["volumes"][0]["source"] = "/tmp/foreign.sock"
    assert effective_orchestration_model_errors(
        payload, spec, recording_sockets={"provision.node.orborus": source}
    )


def _backend(tmp_path, monkeypatch):
    store = _store(tmp_path)
    creation = store.commit(
        store.begin("provision.node.holder", timeout_seconds=60), "a" * 64
    )
    backend = DockerComposeBackend(tmp_path)
    backend._resource_ownership = store.ownership
    backend._resource_attempt_id = store.attempt_id
    backend._docker_daemon_id = store.daemon_id
    native = Native()
    native.containers[creation.native_id] = {
        "Id": creation.native_id,
        "Name": "/worker",
        "Config": {"Labels": {}},
        "State": {"Running": True},
    }
    monkeypatch.setattr(backend, "_recording_native", lambda: native, raising=False)
    monkeypatch.setattr(
        backend,
        "_raw_container_inspect",
        lambda native_id: native.inspect(native_id) or {},
    )
    return backend, store, native, creation


def test_receipted_child_needs_creation_proof_instead_of_workspace_labels(
    tmp_path, monkeypatch
):
    backend, store, _native, creation = _backend(tmp_path, monkeypatch)
    assert backend._resolve_owned_container_id(creation.native_id) == creation.native_id
    backend._resource_attempt_id = "another-attempt"
    with pytest.raises(OwnershipConflictError):
        backend._resolve_owned_container_id(creation.native_id)


def test_project_teardown_removes_verified_unlabelled_children(tmp_path, monkeypatch):
    backend, store, native, creation = _backend(tmp_path, monkeypatch)
    removed = []

    def run(command, **_kwargs):
        assert command[:2] == ["docker", "rm"]
        assert command[-1] == creation.native_id
        removed.append(command[-1])
        del native.containers[command[-1]]
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(backend, "_run", run)
    monkeypatch.setattr(backend, "_finish_docker_recordings", lambda: [], raising=False)
    assert backend.remove_project_containers(remove_volumes=False) == []
    assert removed == [creation.native_id]


def test_cleanup_inspect_failure_retains_receipt_and_performs_no_mutation(
    tmp_path, monkeypatch
):
    backend, store, native, creation = _backend(tmp_path, monkeypatch)
    native.unreadable.add(creation.native_id)
    commands = []
    monkeypatch.setattr(
        backend, "_run", lambda command, **_kwargs: commands.append(command)
    )
    monkeypatch.setattr(backend, "_finish_docker_recordings", lambda: [], raising=False)
    assert backend.remove_project_containers()
    assert commands == []
    assert store.ownership.receipts("container")


def test_unlabelled_recorded_child_counts_as_residual_runtime(tmp_path, monkeypatch):
    backend, _store, _native, _creation = _backend(tmp_path, monkeypatch)
    monkeypatch.setattr(
        backend,
        "_run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 0, "", ""),
    )
    assert backend.observe_project_runtime().container_count == 1


def test_recorded_mount_is_in_the_same_effective_authority_contract(tmp_path):
    backend = DockerComposeBackend(tmp_path)
    spec = _spec()
    source = "/tmp/lilrae-recording-1000/test/root.sock"
    backend._recording_sockets = {"provision.node.orborus": source}
    volumes = backend._recording_service_volumes(spec)
    payload = {"services": {"orborus": {"volumes": list(volumes["orborus"])}}}
    assert not effective_runtime_contract_issues(
        payload, spec, profile=SHARED_DOCKER_PROFILE, validated_service_volumes=volumes
    )
    payload["services"]["orborus"]["volumes"].append(
        {"type": "bind", "source": "/", "target": "/host"}
    )
    assert effective_runtime_contract_issues(
        payload, spec, profile=SHARED_DOCKER_PROFILE, validated_service_volumes=volumes
    )


def test_expected_volume_does_not_mask_an_additional_host_root_mount():
    spec = _spec()
    declared = {"type": "bind", "source": "/declared", "target": "/data"}
    payload = {
        "services": {
            "orborus": {
                "volumes": [
                    declared,
                    {"type": "bind", "source": "/", "target": "/host"},
                ]
            }
        }
    }
    assert effective_runtime_contract_issues(
        payload,
        spec,
        profile=SHARED_DOCKER_PROFILE,
        validated_service_volumes={"orborus": [declared]},
    )


def test_restart_proof_requires_absent_owned_resources_and_no_unresolved_creates(
    tmp_path, monkeypatch
):
    backend, store, native, creation = _backend(tmp_path, monkeypatch)
    monkeypatch.setattr(backend, "_scoped_compose_container_ids", lambda: ())
    assert not backend._recording_restart_allowed(store)
    del native.containers[creation.native_id]
    assert backend._recording_restart_allowed(store)
    store.begin("provision.node.holder", timeout_seconds=60)
    assert not backend._recording_restart_allowed(store)


def test_remote_attempt_without_delegation_reports_complete_empty_inventory():
    from aptl.core.deployment.lilrae_compose_recording import (
        ComposeDockerRecordingMixin,
    )
    from aptl.core.deployment.realization import DeploymentRealizationSpec

    class Remote(ComposeDockerRecordingMixin):
        supports_local_artifacts = False
        _resource_attempt_id = "remote-attempt"

        def _load_resource_ownership(self):
            return None

        def _recording_native(self):
            pytest.fail("remote inventory must not inspect the local daemon")

    backend = Remote()
    assert (
        backend._prepare_docker_recording(DeploymentRealizationSpec((), (), ())) is None
    )
    inventory = backend.runtime_descendant_inventory("remote-attempt")
    assert inventory.complete
    assert not inventory.children
    assert not backend.runtime_descendant_inventory("another-attempt").complete
    failure = backend._prepare_docker_recording(_spec())
    assert failure is not None
    assert not failure.success
    assert not backend.runtime_descendant_inventory("remote-attempt").complete


def test_remote_empty_admission_cannot_erase_retained_child_receipts(
    tmp_path, monkeypatch
):
    from aptl.core.deployment.realization import DeploymentRealizationSpec

    backend, store, native, creation = _backend(tmp_path, monkeypatch)
    monkeypatch.setattr(
        DockerComposeBackend, "supports_local_artifacts", property(lambda self: False)
    )
    assert (
        backend._prepare_docker_recording(DeploymentRealizationSpec((), (), ())) is None
    )
    assert not backend.runtime_descendant_inventory(store.attempt_id).complete
    assert native.containers[creation.native_id]


def test_local_no_delegation_uses_its_empty_admission_not_the_default_socket(
    tmp_path, monkeypatch
):
    from aptl.core.deployment.realization import DeploymentRealizationSpec

    backend = DockerComposeBackend(tmp_path)
    backend._resource_attempt_id = "local-no-delegation"
    backend._docker_socket_path = None
    monkeypatch.setenv("DOCKER_HOST", "unix:///selected/nondefault.sock")
    monkeypatch.setattr(backend, "_load_resource_ownership", lambda: None)
    monkeypatch.setattr(
        backend,
        "_recording_native",
        lambda: pytest.fail("no delegated holder needs no native recorder client"),
    )
    assert (
        backend._prepare_docker_recording(DeploymentRealizationSpec((), (), ())) is None
    )
    observed = backend.runtime_descendant_inventory("local-no-delegation")
    assert observed.complete
    assert not observed.children


def test_native_handoff_retains_original_receipt_and_verified_cleanup(
    tmp_path, monkeypatch
):
    import json
    from aptl.utils.pathsafe import read_contained_nofollow

    backend, store, native, creation = _backend(tmp_path, monkeypatch)
    receipt = creation.receipt()
    original = read_contained_nofollow(
        tmp_path, store.ownership._receipt_path("container", receipt.native_id)
    )

    def remove(command, **kwargs):
        del native.containers[command[-1]]
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(backend, "_run", remove)
    assert backend._remove_recorded_children(remove_volumes=False) == []
    artifacts = backend.native_evidence_artifacts(store.attempt_id)
    assert ("native-resource-receipt/v1", original) in artifacts
    cleanup = [
        json.loads(data) for role, data in artifacts if role == "native-cleanup/v1"
    ]
    assert len(cleanup) == 1
    assert cleanup[0]["native_id"] == receipt.native_id
    assert cleanup[0]["attempt_id"] == store.attempt_id
    assert cleanup[0]["state"] == "absent"
    assert cleanup[0]["cause"] == "after-remove"


def test_native_cleanup_cannot_erase_a_retired_volume_receipt(tmp_path):
    from dataclasses import replace
    from aptl.core.deployment.lilrae_native_evidence import (
        native_evidence_artifacts,
        record_cleanup,
    )

    store = _store(tmp_path)
    creation = store.commit(
        store.begin("provision.node.holder", timeout_seconds=60), "a" * 64
    )
    volume = replace(
        creation.receipt(), kind="volume", native_id="owned-volume", managed_by="direct"
    )
    store.ownership.record(volume)
    record_cleanup(store.ownership, volume, cause="after-remove")
    store.ownership.retire_deleted_volume(volume)
    assert not store.ownership.receipts("volume")
    retained = native_evidence_artifacts(
        store.ownership, store.attempt_id, store.daemon_id
    )
    assert any(
        b'"native_id":"owned-volume"' in data
        for role, data in retained
        if role == "native-resource-receipt/v1"
    )


@pytest.mark.parametrize("kind", ["container", "network", "volume"])
@pytest.mark.parametrize("failure", ["command-failed", "malformed", "still-present"])
def test_ambiguous_native_absence_never_creates_cleanup_proof(tmp_path, kind, failure):
    from aptl.core.deployment._compose_resource_ownership import ResourceReceipt
    from aptl.core.deployment.lilrae_native_evidence import native_evidence_artifacts

    backend = DockerComposeBackend(tmp_path)
    ownership = backend._ensure_resource_ownership(attempt_id="run-a")
    backend._docker_daemon_id = "daemon-a"
    backend._current_docker_daemon_id = lambda: "daemon-a"
    native_id = "volume-a" if kind == "volume" else "a" * 64
    receipt = ResourceReceipt(
        kind=kind,
        native_id=native_id,
        external_name=native_id,
        semantic_name="resource",
        node_address="resource",
        workspace_id=ownership.workspace_id,
        project_name=ownership.project_name,
        daemon_id="daemon-a",
        attempt_id="run-a",
    )
    ownership.record(receipt)
    backend._raw_container_inspect = lambda _: {}
    backend._raw_volume_inspect = lambda _: {}
    backend.host_inspect_network = lambda _: {}
    calls = []

    def run(cmd, **_):
        calls.append(cmd)
        assert "ls" in cmd
        return subprocess.CompletedProcess(
            cmd,
            1 if failure == "command-failed" else 0,
            stdout="invalid response!" if failure == "malformed" else native_id,
            stderr="",
        )

    backend._run = run
    cleanup = {
        "container": lambda: backend._remove_owned_containers("direct"),
        "network": backend.remove_project_networks,
        "volume": backend._remove_owned_volumes,
    }
    assert cleanup[kind]()
    assert ownership.receipts(kind) == (receipt,)
    assert not any(
        role == "native-cleanup/v1"
        for role, _ in native_evidence_artifacts(ownership, "run-a", "daemon-a")
    )
    assert calls
