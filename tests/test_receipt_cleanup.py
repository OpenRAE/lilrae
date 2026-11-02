"""Native declared cleanup uses real receipt validation, with fake transport."""

import subprocess

import pytest

from aptl.core.cleanup import CleanupBinding
from aptl.core.deployment.declared_cleanup import ReceiptCleanup
from aptl.core.deployment._compose_resource_ownership import (
    ResourceReceipt,
    WorkspaceOwnership,
)
from aptl.core.deployment.docker_compose import DockerComposeBackend
from aptl.core.deployment.lilrae_recorded_inventory import RecordedInventorySnapshot


class NativeBackend(DockerComposeBackend):
    def __init__(self, root):
        super().__init__(root)
        self.owner = WorkspaceOwnership.ensure(root, "aptl")
        self._resource_ownership = self.owner
        self._resource_attempt_id = "native-a"
        self._docker_daemon_id = "daemon-a"
        self.live = {}
        self.removed = []
        self.inspection_failed = False
        self.gap = False

    def _current_docker_daemon_id(self):
        return self._docker_daemon_id

    def _raw_container_inspect(self, native_id):
        if self.inspection_failed:
            raise OSError("sensitive backend detail")
        return self.live.get(native_id, {})

    def _quiesce_docker_recordings(self, attempt_id=None):
        assert attempt_id == "native-a"
        return ["private native detail"] if self.gap else []

    def _finish_docker_recordings(self, attempt_id=None):
        return []

    def runtime_descendant_inventory(self, attempt_id):
        return RecordedInventorySnapshot(complete=not self.gap)

    def _run(self, command, *, timeout=None):
        if command[:3] == ["docker", "rm", "-f"]:
            self.removed.append(tuple(command))
            self.live.pop(command[-1], None)
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:3] == ["docker", "container", "ls"]:
            wanted = command[command.index("--filter") + 1].removeprefix("id=")
            return subprocess.CompletedProcess(
                command, 0, wanted if wanted in self.live else "", ""
            )
        raise AssertionError(command)

    def add(self, native_id, *, attempt_id="native-a", foreign=False):
        receipt = ResourceReceipt(
            "container",
            native_id,
            "victim",
            "victim",
            "node.a",
            self.owner.workspace_id,
            self.owner.project_name,
            "daemon-a",
            attempt_id,
        )
        self.owner.record(receipt)
        self.live[native_id] = {
            "Id": native_id,
            "Name": "/victim",
            "Config": {
                "Labels": {} if foreign else self.owner.labels(attempt_id=attempt_id)
            },
        }


def setup_cleanup(tmp_path):
    backend = NativeBackend(tmp_path)
    backend.add("a" * 64)
    binding = CleanupBinding(
        "entry-a",
        "run-a",
        "exec-a",
        "native-a",
        "range-a",
        "apparatus:range-a",
        ("node.a",),
        tmp_path,
    )
    return ReceiptCleanup(backend, binding), backend


def test_destroy_is_native_id_pinned_repeatable_and_does_not_remove_implicit_volumes(
    tmp_path,
):
    cleanup, backend = setup_cleanup(tmp_path)
    foreign_file = tmp_path / "unrelated.txt"
    foreign_file.write_text("keep")
    backend.add("b" * 64, attempt_id="prior-attempt")
    assert cleanup.execute("destroy", 120).absent
    assert cleanup.execute("destroy", 120).absent
    assert backend.removed == [("docker", "rm", "-f", "a" * 64)]
    assert "b" * 64 in backend.live
    assert foreign_file.read_text() == "keep"


@pytest.mark.parametrize(
    "failure", ["foreign", "inspection", "daemon", "gap", "attempt"]
)
def test_ambiguous_authority_has_no_destructive_fallback(tmp_path, failure):
    cleanup, backend = setup_cleanup(tmp_path)
    if failure == "foreign":
        backend.live["a" * 64]["Config"]["Labels"] = {}
    elif failure == "inspection":
        backend.inspection_failed = True
    elif failure == "daemon":
        backend._docker_daemon_id = "other-daemon"
    elif failure == "gap":
        backend.gap = True
    else:
        backend._resource_attempt_id = "prior-attempt"
    result = cleanup.execute("destroy", 120)
    assert not result.absent
    assert result.reasons
    assert backend.removed == []


def test_a_replaced_workspace_cannot_supply_cleanup_authority(tmp_path):
    cleanup, backend = setup_cleanup(tmp_path)
    replacement = WorkspaceOwnership.ensure(tmp_path / "foreign", "aptl")
    state = ".aptl/lifecycle/workspace-ownership-v1.json"
    (tmp_path / state).write_bytes((replacement.root / state).read_bytes())
    assert not cleanup.execute("destroy", 120).absent
    assert backend.removed == []


def test_verification_is_read_only_even_after_resources_were_removed(tmp_path):
    cleanup, backend = setup_cleanup(tmp_path)
    assert cleanup.execute("destroy", 120).absent
    before = sorted(tmp_path.rglob("*.json"))
    assert cleanup.execute("verify", 120).absent
    assert sorted(tmp_path.rglob("*.json")) == before


def test_authored_budget_prevents_a_second_effect_after_the_first_uses_it(tmp_path):
    cleanup, backend = setup_cleanup(tmp_path)
    backend.add("c" * 64)
    elapsed = [0.0]
    original = backend._run

    def timed_run(command, *, timeout=None):
        result = original(command, timeout=timeout)
        if command[:3] == ["docker", "rm", "-f"]:
            elapsed[0] += 1
        return result

    backend._run = timed_run
    cleanup = ReceiptCleanup(backend, cleanup.binding, clock=lambda: elapsed[0])
    result = cleanup.execute("destroy", 1)
    assert len(backend.removed) == 1
    assert not result.absent
    assert {resource.native_id for resource in result.resources} == {"a" * 64, "c" * 64}


def test_child_coverage_gap_blocks_even_read_only_clean_certification(tmp_path):
    cleanup, backend = setup_cleanup(tmp_path)
    assert cleanup.execute("destroy", 120).absent
    backend.gap = True
    assert not cleanup.execute("verify", 120).absent


def test_recorder_shutdown_cannot_certify_success_after_the_deadline(tmp_path):
    cleanup, backend = setup_cleanup(tmp_path)
    elapsed = [0.0]

    def shutdown(attempt_id=None):
        elapsed[0] = 121
        return []

    backend._finish_docker_recordings = shutdown
    cleanup = ReceiptCleanup(backend, cleanup.binding, clock=lambda: elapsed[0])
    assert not cleanup.execute("destroy", 120).absent
