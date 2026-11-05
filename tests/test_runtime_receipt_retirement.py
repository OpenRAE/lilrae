"""Teardown retires the receipts of removed containers and networks (#1478).

A stop, an emergency kill, and a failed-start rollback retire a receipt only
after a bounded listing on the receipt's daemon proves its object absent and
the attempt evidence retains the receipt and an absence witness.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from aptl.core.deployment import lilrae_native_evidence
from aptl.core.deployment._compose_lifecycle import kill_compose_lab
from aptl.core.deployment._compose_resource_ownership import (
    OwnershipConflictError,
    ResourceReceipt,
    WorkspaceOwnership,
)
from aptl.core.deployment._compose_stop import stop_compose_lab
from aptl.core.deployment.backend_host_inventory import ProjectRuntimePresence
from aptl.core.deployment.docker_compose import DockerComposeBackend
from aptl.core.deployment.lilrae_native_evidence import (
    native_evidence_artifacts,
    record_cleanup,
)

_CHILD_ID = "a" * 64
_OTHER_DAEMON_ID = "b" * 64


class _ReusedProjectDaemon:
    """One daemon that a reused project starts and tears down repeatedly."""

    def __init__(self, backend: DockerComposeBackend) -> None:
        self.ownership = backend._ensure_resource_ownership(attempt_id="run-0")
        self.containers: dict[str, dict[str, object]] = {}
        self.networks: dict[str, dict[str, object]] = {}
        self.stuck: set[str] = set()
        self.failing: set[tuple[str, ...]] = set()
        self.container_inspects = 0
        backend._docker_daemon_id = "daemon-a"
        backend._current_docker_daemon_id = lambda: "daemon-a"
        backend._raw_container_inspect = self.inspect_container
        backend.host_inspect_network = lambda native_id: self.networks.get(
            native_id, {}
        )
        backend._recorded_child_is_current = lambda receipt, recovery=False: False
        backend._run = self.run
        backend._build_command = lambda action, *args, **kwargs: [
            "docker",
            "compose",
            action,
        ]
        backend.remove_stranded_helpers = lambda: []
        backend.observe_project_runtime = self.presence

    def receipt(self, kind: str, native_id: str, attempt: int, **extra: str):
        """Return a receipt of this workspace on daemon-a."""

        name = (
            self.ownership.container_name("victim")
            if kind == "container"
            else f"{self.ownership.project_name}_lab-net"
        )
        fields = {
            "kind": kind,
            "native_id": native_id,
            "external_name": name,
            "semantic_name": "victim" if kind == "container" else "lab-net",
            "node_address": "victim" if kind == "container" else "lab-net",
            "workspace_id": self.ownership.workspace_id,
            "project_name": self.ownership.project_name,
            "daemon_id": "daemon-a",
            "attempt_id": f"run-{attempt}",
            "managed_by": "compose",
        }
        return ResourceReceipt(**{**fields, **extra})

    def start(self, attempt: int) -> str:
        """Create and record one Compose container and network; return the ID."""

        container_id, network_id = f"c{attempt:063x}", f"e{attempt:063x}"
        container = self.receipt("container", container_id, attempt)
        network = self.receipt("network", network_id, attempt)
        self.ownership.record(container)
        self.ownership.record(network)
        self.containers[container_id] = {
            "Id": container_id,
            "Name": f"/{container.external_name}",
            "Config": {
                "Labels": {
                    "aptl.workspace.id": self.ownership.workspace_id,
                    "aptl.lifecycle.project": self.ownership.project_name,
                }
            },
        }
        self.networks[network_id] = {
            "id": network_id,
            "name": network.external_name,
            "labels": {"com.docker.compose.project": self.ownership.project_name},
        }
        return container_id

    def inspect_container(self, native_id: str) -> dict[str, object]:
        """Count one ``docker inspect`` and return the current object, if any."""

        self.container_inspects += 1
        return self.containers.get(native_id, {})

    def run(self, cmd: list[str], *, timeout: int | None = None):
        """Apply teardown commands and bounded listings to the daemon state."""

        del timeout
        if any(tuple(cmd[: len(prefix)]) == prefix for prefix in self.failing):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="failed")
        stdout = ""
        if cmd[:2] == ["docker", "rm"] and cmd[-1] not in self.stuck:
            self.containers.pop(cmd[-1], None)
        elif cmd[:3] == ["docker", "network", "rm"] and cmd[-1] not in self.stuck:
            self.networks.pop(cmd[-1], None)
        elif cmd[:2] == ["docker", "compose"]:
            for objects in (self.containers, self.networks):
                for native_id in set(objects) - self.stuck:
                    del objects[native_id]
        elif cmd[:3] in (["docker", "container", "ls"], ["docker", "network", "ls"]):
            wanted = cmd[cmd.index("--filter") + 1].removeprefix("id=")
            objects = self.containers if cmd[1] == "container" else self.networks
            stdout = wanted if wanted in objects else ""
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    def presence(self) -> ProjectRuntimePresence:
        """Report the checked runtime presence of this project."""

        return ProjectRuntimePresence(
            container_count=len(self.containers), network_count=len(self.networks)
        )

    def native_ids(self, kind: str) -> set[str]:
        """Return the native IDs of the live receipts of one kind."""

        return {receipt.native_id for receipt in self.ownership.receipts(kind)}


def _teardown(backend: DockerComposeBackend, teardown: str) -> bool:
    """Run one stop or emergency kill and return whether it succeeded."""

    if teardown == "stop":
        return stop_compose_lab(backend, [], remove_volumes=False, timeout=30).success
    return kill_compose_lab(backend, [], timeout=30)[0]


def _witnesses(ownership: WorkspaceOwnership, attempt_id: str) -> list[Path]:
    """Return the absence witness files of one attempt."""

    directory = (
        ownership.root
        / lilrae_native_evidence._directory(attempt_id)
        / "cleanup"
    )
    return sorted(directory.glob("*.json")) if directory.is_dir() else []


def _witness_of(ownership: WorkspaceOwnership, receipt: ResourceReceipt) -> Path:
    """Return the path of the absence witness of one receipt."""

    digest = hashlib.sha256(lilrae_native_evidence._receipt_bytes(receipt))
    directory = ownership.root / lilrae_native_evidence._directory(receipt.attempt_id)
    return directory / "cleanup" / f"{digest.hexdigest()}.json"


@pytest.fixture
def daemon(tmp_path: Path) -> tuple[DockerComposeBackend, _ReusedProjectDaemon]:
    backend = DockerComposeBackend(tmp_path, project_name="aptl")
    return backend, _ReusedProjectDaemon(backend)


@pytest.mark.parametrize("teardown", ["stop", "kill"])
@pytest.mark.parametrize("earlier_starts", [1, 8])
def test_resolution_cost_stays_flat_across_starts_in_a_reused_project(
    daemon, teardown: str, earlier_starts: int
) -> None:
    """Teardown retires removed receipts; volumes and child receipts stay."""

    backend, lab = daemon
    volume = ResourceReceipt(
        **{
            **lab.receipt("container", _CHILD_ID, 0).__dict__,
            "kind": "volume",
            "native_id": f"{lab.ownership.project_name}_data",
            "external_name": f"{lab.ownership.project_name}_data",
            "managed_by": "direct",
        }
    )
    child = lab.receipt("container", _CHILD_ID, 0, managed_by="child")
    lab.ownership.record(volume)
    lab.ownership.record(child)
    for attempt in range(1, earlier_starts + 1):
        lab.start(attempt)
        assert _teardown(backend, teardown)
    current = lab.start(earlier_starts + 1)
    lab.container_inspects = 0

    assert backend._resolve_owned_container_id("victim") == current
    assert lab.container_inspects == 1
    assert lab.native_ids("container") == {current, _CHILD_ID}
    assert lab.native_ids("network") == {f"e{earlier_starts + 1:063x}"}
    assert lab.ownership.receipts("volume") == (volume,)
    # Every stop observes the absent child again; its witness stays one file.
    assert len(_witnesses(lab.ownership, "run-0")) == 1


@pytest.mark.parametrize("teardown", ["stop", "kill"])
def test_retired_receipts_stay_in_the_attempt_evidence(daemon, teardown: str) -> None:
    """Evidence export still holds each retired receipt and its witness."""

    backend, lab = daemon
    lab.start(1)
    retired = lab.ownership.receipts("container") + lab.ownership.receipts("network")

    assert _teardown(backend, teardown)

    assert lab.native_ids("container") == lab.native_ids("network") == set()
    artifacts = native_evidence_artifacts(lab.ownership, "run-1", "daemon-a")
    receipts = {data for role, data in artifacts if role == "native-resource-receipt/v1"}
    assert receipts == {lilrae_native_evidence._receipt_bytes(r) for r in retired}
    assert [role for role, _ in artifacts].count("native-cleanup/v1") == 2


@pytest.mark.parametrize("teardown", ["stop", "kill"])
def test_teardown_keeps_receipts_that_evidence_cannot_retain(
    daemon, monkeypatch, teardown: str
) -> None:
    """A failed evidence write keeps the live receipt, even with no residue."""

    backend, lab = daemon
    lab.start(1)
    before = lab.native_ids("container") | lab.native_ids("network")

    def unavailable(*args, **kwargs):
        raise OSError("evidence store is unavailable")

    monkeypatch.setattr(lilrae_native_evidence, "record_cleanup", unavailable)

    assert not _teardown(backend, teardown)
    assert lab.presence() == ProjectRuntimePresence()
    assert lab.native_ids("container") | lab.native_ids("network") == before


@pytest.mark.parametrize(
    ("kind", "failing"),
    [
        ("container", ("docker", "rm")),
        ("container", ("docker", "container", "ls")),
        ("network", ("docker", "network", "rm")),
        ("network", ("docker", "network", "ls")),
    ],
)
def test_teardown_keeps_receipts_without_proven_absence(
    daemon, kind: str, failing: tuple[str, ...]
) -> None:
    """Residue or a failed listing proves nothing absent, so that receipt stays."""

    backend, lab = daemon
    lab.start(1)
    (receipt,) = lab.ownership.receipts(kind)
    lab.stuck.add(receipt.native_id)
    lab.failing.add(failing)

    assert not _teardown(backend, "stop")
    assert receipt in lab.ownership.receipts(kind)
    assert not _witness_of(lab.ownership, receipt).exists()


def test_teardown_keeps_a_receipt_bound_to_another_daemon(daemon) -> None:
    """Cleanup refuses a receipt from another daemon and keeps it."""

    backend, lab = daemon
    other = lab.receipt("network", _OTHER_DAEMON_ID, 0, daemon_id="daemon-b")
    lab.ownership.record(other)

    assert not _teardown(backend, "stop")
    assert other in lab.ownership.receipts("network")


def test_failed_start_rollback_retires_the_removed_attempt_receipts(daemon) -> None:
    """Rollback retires a container receipt once removal is proven."""

    backend, lab = daemon
    removed = lab.start(1)
    kept = lab.start(2)

    backend._remove_owned_attempt_containers("run-1")

    assert lab.native_ids("container") == {kept}
    assert removed not in lab.containers
    assert len(_witnesses(lab.ownership, "run-1")) == 1


def test_removed_resource_retirement_refuses_unproven_or_changed_receipts(
    daemon,
) -> None:
    """Retirement needs the exact container or network receipt, not a child."""

    _, lab = daemon
    lab.start(1)
    container = lab.ownership.receipts("container")[0]
    child = lab.receipt("container", _CHILD_ID, 0, managed_by="child")
    lab.ownership.record(child)

    for receipt, message in (
        (
            ResourceReceipt(**{**container.__dict__, "attempt_id": "run-other"}),
            "receipt conflicts",
        ),
        (ResourceReceipt(**{**container.__dict__, "kind": "volume"}), "scope"),
        (child, "scope"),
    ):
        with pytest.raises(OwnershipConflictError, match=message):
            lab.ownership.retire_removed_resource(receipt)
    assert lab.native_ids("container") == {container.native_id, _CHILD_ID}


def test_a_repeated_absence_witness_adds_no_file(daemon) -> None:
    """The first witness of a receipt stays; a conflicting one is refused."""

    _, lab = daemon
    lab.start(1)
    receipt = lab.ownership.receipts("container")[0]

    record_cleanup(lab.ownership, receipt, cause="after-remove")
    record_cleanup(lab.ownership, receipt, cause="already-absent")

    (witness,) = _witnesses(lab.ownership, "run-1")
    assert b'"cause":"after-remove"' in witness.read_bytes()
    witness.write_bytes(witness.read_bytes().replace(b"run-1", b"run-x"))
    with pytest.raises(OwnershipConflictError, match="witness conflicts"):
        record_cleanup(lab.ownership, receipt, cause="already-absent")
