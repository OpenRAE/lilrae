"""Exact Docker realization of SDL ``container.autoremove`` semantics."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from raes.runtime_configuration import RuntimeConfiguration

from aptl.core.deployment._compose_resource_ownership import ResourceReceipt
from aptl.core.deployment.docker_compose import DockerComposeBackend
from aptl.core.deployment.observation import DeploymentObservationContext
from aptl.core.deployment.realization import (
    DeploymentImageRealization,
    DeploymentNodeRealization,
    DeploymentRealizationSpec,
)
from aptl.core.lab_types import LabResult

_CONTAINER = "aptl-init"
_ADDRESS = "provision.node.init"
_IMAGE_DIGEST = "sha256:" + "a" * 64
_NATIVE_ID = "c" * 64
_IMAGE_ID = "sha256:" + "d" * 64
_OS_RELEASE = b'ID="debian"\nVERSION_ID="12"\n'
_IMAGE_OF = ("docker", "inspect", "--format", "{{.Image}}")
_REPO_DIGESTS_OF = ("docker", "image", "inspect", "--format", "{{json .RepoDigests}}")


def _runtime(*, autoremove: bool) -> RuntimeConfiguration:
    return RuntimeConfiguration.model_validate(
        {
            "container": {
                "autoremove": autoremove,
                "entrypoint": ["/bin/init"],
            }
        }
    )


def _spec(*, autoremove: bool = True) -> DeploymentRealizationSpec:
    return DeploymentRealizationSpec(
        profiles=(),
        nodes=(
            DeploymentNodeRealization(
                address=_ADDRESS,
                name="init",
                service_name="init",
                container_name=_CONTAINER,
                networks=(),
                os="linux",
                runtime=_runtime(autoremove=autoremove),
            ),
        ),
        networks=(),
        images=(
            DeploymentImageRealization(
                address=_ADDRESS,
                service_name="init",
                source_name="example/init",
                source_version=_IMAGE_DIGEST,
                image_ref=f"example/init@{_IMAGE_DIGEST}",
                mode="pull",
                policy_rule="authored-exact-artifact",
            ),
        ),
    )


def _completed_inspect(external_name: str, labels: dict[str, str]) -> dict[str, object]:
    return {
        "Id": _NATIVE_ID,
        "Name": f"/{external_name}",
        "State": {"Running": False, "Status": "exited", "ExitCode": 0},
        "Platform": "linux",
        "Config": {"Entrypoint": ["/bin/init"], "Labels": labels},
        "HostConfig": {
            "AutoRemove": False,
            "RestartPolicy": {"Name": "no"},
        },
        "Mounts": [],
    }


class _FakeDocker:
    """Answer the Docker CLI for one recorded, exited init container.

    Only ``subprocess.run`` is replaced, so the backend's receipt resolver,
    ``container_inspect`` and raw inspect run unmodified. ``docker rm`` exits
    with ``rm_exit``; a zero exit deletes the container unless ``removes`` is
    false.
    """

    def __init__(
        self, inspect: dict[str, object], *, rm_exit: int = 0, removes: bool = True
    ) -> None:
        self.inspect = inspect
        self.rm_exit = rm_exit
        self.removes = removes
        self.present = True
        self.removals: list[list[str]] = []

    def __call__(
        self, argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess:
        stdout = None
        if argv[:2] == ["docker", "rm"]:
            assert kwargs.get("timeout") is not None
            self.removals.append(argv)
            if self.rm_exit:
                return subprocess.CompletedProcess(
                    argv, self.rm_exit, "", "private daemon detail"
                )
            self.present = self.present and not self.removes
            stdout = ""
        elif argv == [*_REPO_DIGESTS_OF, _IMAGE_ID]:
            stdout = json.dumps([f"example/init@{_IMAGE_DIGEST}"])
        elif self.present:
            stdout = self._container_read(argv)
        if stdout is None:
            return subprocess.CompletedProcess(argv, 1, "", "Error: No such object")
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    def _container_read(self, argv: list[str]) -> str | None:
        if argv == ["docker", "inspect", _NATIVE_ID]:
            return json.dumps([self.inspect])
        if argv == [*_IMAGE_OF, _NATIVE_ID]:
            return _IMAGE_ID
        if argv[:3] == ["docker", "cp", f"{_NATIVE_ID}:/etc/os-release"]:
            Path(argv[3]).write_bytes(_OS_RELEASE)
            return ""
        return None


@pytest.fixture
def recorded_init(tmp_path):
    """Return a real backend holding a Compose receipt, and the exited inspect."""

    backend = DockerComposeBackend(tmp_path, project_name="aptl-test")
    backend._docker_daemon_id = "daemon-a"
    ownership = backend._ensure_resource_ownership(attempt_id="run-a")
    external_name = ownership.container_name(_CONTAINER)
    ownership.record(
        ResourceReceipt(
            kind="container",
            native_id=_NATIVE_ID,
            external_name=external_name,
            semantic_name=_CONTAINER,
            node_address=_ADDRESS,
            workspace_id=ownership.workspace_id,
            project_name=ownership.project_name,
            daemon_id="daemon-a",
            attempt_id="run-a",
            managed_by="compose",
        )
    )
    labels = {
        "aptl.workspace.id": ownership.workspace_id,
        "aptl.lifecycle.project": ownership.project_name,
        "com.docker.compose.project": ownership.project_name,
    }
    return backend, _completed_inspect(external_name, labels)


def test_completed_autoremove_container_is_removed_and_receipted(recorded_init):
    backend, inspect = recorded_init
    context = DeploymentObservationContext()
    docker = _FakeDocker(inspect)

    with patch("subprocess.run", side_effect=docker):
        failures = backend._retire_completed_autoremove_nodes(_spec(), context)

    assert failures == []
    # Not forced: a still-running container must refuse removal here, not
    # be killed. ``-v`` takes its anonymous volumes with it; without it they
    # outlive the container with nothing left to attribute them to the lab.
    assert docker.removals == [["docker", "rm", "-v", _NATIVE_ID]]
    assert context.autoremove_verified(_CONTAINER) is True
    assert context.completed_inspect(_CONTAINER) == inspect
    assert context.completed_image_digest(_CONTAINER) == _IMAGE_DIGEST
    assert (
        context.completed_file_read(_CONTAINER, "/etc/os-release", max_bytes=64 * 1024)
        == _OS_RELEASE
    )


@pytest.mark.parametrize(
    ("rm_exit", "failure"),
    [(1, "could not be auto-removed"), (0, "remained after auto-remove")],
    ids=["rm-fails", "container-remains"],
)
def test_autoremove_failure_is_fail_closed_and_has_no_receipt(
    recorded_init, rm_exit, failure
):
    backend, inspect = recorded_init
    context = DeploymentObservationContext()
    docker = _FakeDocker(inspect, rm_exit=rm_exit, removes=False)

    with patch("subprocess.run", side_effect=docker):
        failures = backend._retire_completed_autoremove_nodes(_spec(), context)

    assert failures == [f"container {_CONTAINER!r} {failure}"]
    assert "private daemon detail" not in failures[0]
    assert context.autoremove_verified(_CONTAINER) is False


def test_container_without_autoremove_is_not_removed(tmp_path):
    backend = DockerComposeBackend(tmp_path, project_name="aptl-test")
    with patch.object(backend, "_run") as run:
        assert (
            backend._retire_completed_autoremove_nodes(
                _spec(autoremove=False), DeploymentObservationContext()
            )
            == []
        )
    run.assert_not_called()


def test_post_start_fails_when_completed_container_cannot_be_removed(tmp_path):
    backend = DockerComposeBackend(tmp_path, project_name="aptl-test")
    context = DeploymentObservationContext()
    with (
        patch.object(backend, "_reconcile_realization_networks", return_value=[]),
        patch.object(backend, "_await_realized_service_health", return_value=[]),
        patch.object(
            backend, "_verify_stateful_authenticated_readiness", return_value=None
        ),
        patch.object(backend, "_verify_runtime_orchestration", return_value=None),
        patch.object(backend, "_realize_accounts_step", return_value=None),
        patch.object(
            backend,
            "_retire_completed_autoremove_nodes",
            return_value=["container 'aptl-init' could not be auto-removed"],
        ),
    ):
        result = backend._post_start_result(_spec(), context)

    assert result == LabResult(
        success=False,
        error="container 'aptl-init' could not be auto-removed",
    )
