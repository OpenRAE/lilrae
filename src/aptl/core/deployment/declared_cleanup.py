"""Complete-attempt native cleanup under existing workspace receipt authority."""

from collections.abc import Callable
from time import monotonic

from aptl.core.cleanup import (
    CleanupAction,
    CleanupBinding,
    CleanupReadback,
    CleanupResourceState,
)
from aptl.core.deployment._cleanup_budget import cleanup_budget, CleanupDeadline
from aptl.core.deployment._compose_resource_ownership import (
    OwnershipConflictError,
    ResourceReceipt,
    WorkspaceOwnership,
    _decode_receipt,
)
from aptl.core.deployment.docker_compose import DockerComposeBackend
from aptl.core.deployment.errors import BackendTimeoutError
from aptl.core.deployment.lilrae_native_evidence import (
    confirm_native_absence,
    record_cleanup,
)
from aptl.core.lifecycle_guard import lifecycle_mutation_lock
from aptl.core.ephemeral_containers import remove_container_command


class ReceiptCleanup:
    """Trusted composition grants one complete attempt, never an authored selector."""

    def __init__(
        self,
        backend: DockerComposeBackend,
        binding: CleanupBinding,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.backend, self.binding, self.clock = backend, binding, clock
        ownership = backend._load_resource_ownership()
        if ownership is None or ownership.root != binding.project_dir.resolve():
            raise OwnershipConflictError("cleanup workspace binding is unavailable")
        self._ownership = ownership
        self._daemon_id = backend._docker_daemon_id
        if not self._daemon_id:
            raise OwnershipConflictError("cleanup daemon binding is unavailable")

    def execute(self, action: CleanupAction, timeout_seconds: int) -> CleanupReadback:
        """Revalidate authority, drain producers, and operate only on native IDs."""
        if action not in {"destroy", "verify"}:
            raise ValueError("native cleanup action is unsupported")
        try:
            with (
                lifecycle_mutation_lock(self.binding.project_dir),
                cleanup_budget(timeout_seconds, self.clock) as budget,
            ):
                return self._execute_owned(action, budget)
        except (
            OwnershipConflictError,
            BackendTimeoutError,
            OSError,
            ValueError,
            BufferError,
        ):
            return CleanupReadback((), ("native-cleanup-authority-unverified",))

    def _require_authority(self) -> WorkspaceOwnership:
        current = WorkspaceOwnership.load(
            self.binding.project_dir, self._ownership.logical_project_name
        )
        if (
            current != self._ownership
            or self.backend._resource_attempt_id != self.binding.native_attempt_id
            or self.backend._current_docker_daemon_id() != self._daemon_id
        ):
            raise OwnershipConflictError("cleanup native scope changed")
        return current

    def _receipts(self, ownership: WorkspaceOwnership) -> tuple[ResourceReceipt, ...]:
        current = {
            (receipt.kind, receipt.native_id): receipt
            for kind in ("container", "network", "volume")
            for receipt in ownership.receipts(kind)
            if receipt.attempt_id == self.binding.native_attempt_id
        }
        # Volume retirement removes live authority. Retained immutable receipts
        # permit absence checks only, never deletion of a recreated volume.
        retained = dict(current)
        for kind, data in self.backend.native_evidence_artifacts(
            self.binding.native_attempt_id
        ):
            if kind == "native-resource-receipt/v1":
                receipt = _decode_receipt(data)
                retained.setdefault((receipt.kind, receipt.native_id), receipt)
        if len(retained) > 4096:
            raise BufferError("cleanup receipt inventory exceeds its bound")
        self._active_receipts = current
        for receipt in retained.values():
            if (
                receipt.workspace_id != ownership.workspace_id
                or receipt.project_name != ownership.project_name
                or receipt.daemon_id != self._daemon_id
                or receipt.attempt_id != self.binding.native_attempt_id
            ):
                raise OwnershipConflictError("cleanup receipt scope changed")
        return tuple(
            sorted(
                retained.values(),
                key=lambda receipt: (
                    {"container": 0, "network": 1, "volume": 2}[receipt.kind],
                    receipt.native_id,
                ),
            )
        )

    def _execute_owned(
        self, action: CleanupAction, budget: CleanupDeadline
    ) -> CleanupReadback:
        ownership = self._require_authority()
        if self._creation_unresolved(action):
            return CleanupReadback((), ("native-creation-unresolved",))
        budget.remaining()
        receipts = self._receipts(ownership)
        if not receipts:
            return CleanupReadback((), ("native-inventory-unverified",))
        # Preflight every receipt before the first effect. A foreign or unreadable
        # member prevents deleting an otherwise valid part of an ambiguous scope.
        for receipt in receipts:
            self._present(ownership, receipt, budget)
        states = []
        for receipt in receipts:
            try:
                states.append(self._cleanup_one(action, ownership, receipt, budget))
            except (
                OwnershipConflictError,
                BackendTimeoutError,
                OSError,
                ValueError,
                BufferError,
            ):
                states.append(
                    CleanupResourceState(receipt.kind, receipt.native_id, "unverified")
                )
        reasons = ()
        if action == "destroy" and self.backend._finish_docker_recordings(
            self.binding.native_attempt_id
        ):
            reasons = ("native-recording-stop-unverified",)
        try:
            budget.remaining()
        except BackendTimeoutError:
            reasons = (*reasons, "native-cleanup-deadline-expired")
        return CleanupReadback(tuple(states), reasons)

    def _creation_unresolved(self, action: CleanupAction) -> bool:
        if action == "destroy" and self.backend._quiesce_docker_recordings(
            self.binding.native_attempt_id
        ):
            return True
        return not self.backend.runtime_descendant_inventory(
            self.binding.native_attempt_id
        ).complete

    def _cleanup_one(
        self,
        action: CleanupAction,
        ownership: WorkspaceOwnership,
        receipt: ResourceReceipt,
        budget: CleanupDeadline,
    ) -> CleanupResourceState:
        budget.remaining()
        present = self._present(ownership, receipt, budget)
        if present and action == "destroy":
            self._require_authority()
            commands = {
                "container": remove_container_command(
                    receipt.native_id, remove_volumes=False
                ),
                "network": ["docker", "network", "rm", receipt.native_id],
                "volume": ["docker", "volume", "rm", receipt.native_id],
            }
            removed = self.backend._run(
                commands[receipt.kind], timeout=budget.remaining()
            )
            if removed.returncode:
                return CleanupResourceState(receipt.kind, receipt.native_id, "present")
            present = self._present(ownership, receipt, budget)
        if (
            action == "destroy"
            and not present
            and (receipt.kind, receipt.native_id) in self._active_receipts
        ):
            record_cleanup(ownership, receipt, cause="after-remove")
            if receipt.kind == "volume":
                ownership.retire_deleted_volume(receipt)
        return CleanupResourceState(
            receipt.kind, receipt.native_id, "present" if present else "absent"
        )

    def _present(
        self,
        ownership: WorkspaceOwnership,
        receipt: ResourceReceipt,
        budget: CleanupDeadline,
    ) -> bool:
        budget.remaining()
        self._require_authority()
        checks = {
            "container": self.backend._container_receipt_is_current,
            "network": self.backend._network_receipt_is_current,
            "volume": self.backend._volume_receipt_is_current,
        }
        present = checks[receipt.kind](ownership, receipt)
        if present and (receipt.kind, receipt.native_id) not in self._active_receipts:
            raise OwnershipConflictError("a retired native resource was replaced")
        if not present and not confirm_native_absence(self.backend, receipt):
            raise OwnershipConflictError("native resource absence is unverified")
        return present
