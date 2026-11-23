"""Native creation recording integrated with the existing Compose lifecycle."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from aptl.core.deployment._compose_resource_ownership import (
    OwnershipConflictError,
    ResourceReceipt,
    WorkspaceOwnership,
)
from aptl.core.deployment._compose_runtime_orchestration import (
    docker_authority_admissions,
)
from aptl.core.deployment.lilrae_docker_http import NativeDocker
from aptl.core.deployment.lilrae_docker_recorder import (
    RecordingSession,
    existing_sessions,
    start_recording,
)
from aptl.core.deployment.lilrae_docker_recording import RecordingStore
from aptl.core.deployment.lilrae_recorded_inventory import (
    RecordedInventory,
    RecordedInventorySnapshot,
)
from aptl.core.ephemeral_containers import remove_container_command
from aptl.core.lab_types import LabResult
from aptl.core.deployment.errors import BackendTimeoutError
from aptl.utils.pathsafe import PathContainmentError, replace_private_nofollow

if TYPE_CHECKING:
    from aptl.core.deployment.realization import DeploymentRealizationSpec
    from aptl.runtime_authority import DeploymentDockerAuthorityAdmission


_RECORDING_UNAVAILABLE = ("native-recording-unavailable",)


def _live_session_status(
    ownership: WorkspaceOwnership, attempt_id: str
) -> dict[str, object] | None:
    """Return the status of the first live recording session for an attempt."""
    for session in existing_sessions(ownership):
        if session.store.attempt_id == attempt_id:
            status = session.status()
            if status is not None:
                return status
    return None


def _drain_failures(session: RecordingSession) -> list[str]:
    """Drain one recording session and return its unresolved failures."""
    failures: list[str] = []
    try:
        if session.status() is not None:
            failures.extend(session.quiesce())
        session.store.recover_responses()
        if session.store.pending():
            failures.append("a recorded Docker create has an unresolved native outcome")
        if session.store.gaps():
            failures.append("Docker descendant recording has unresolved coverage gaps")
    except (
        OSError,
        ValueError,
        OwnershipConflictError,
        PathContainmentError,
    ):
        failures.append("recorded Docker creation drain is unavailable")
    return failures


class ComposeDockerRecordingMixin:
    """Add Docker creation recording to the Compose lab backend."""

    def native_evidence_artifacts(
        self, attempt_id: str
    ) -> tuple[tuple[str, bytes], ...]:
        """Expose producer bytes without granting a collector native access."""
        from aptl.core.deployment.lilrae_native_evidence import (
            native_evidence_artifacts,
        )

        ownership = self._load_resource_ownership()
        if ownership is None or not self._docker_daemon_id:
            raise OwnershipConflictError("native evidence owner is unavailable")
        return native_evidence_artifacts(ownership, attempt_id, self._docker_daemon_id)

    def _recording_native(self) -> NativeDocker:
        """Return a Docker client bound to the verified recording daemon."""
        socket_path = self._docker_socket_path
        if not socket_path:
            raise OwnershipConflictError("recording daemon endpoint is not bound")
        return NativeDocker(
            socket_path,
            self._ownership_daemon_id(),
            identity=self._docker_socket_identity,
        )

    def _prepare_docker_recording(
        self, realization: DeploymentRealizationSpec
    ) -> LabResult | None:
        """Start creation recording for admitted nodes, or return the failure."""
        admissions = docker_authority_admissions(realization)
        self._recording_empty_attempt = None
        if not admissions:
            self._recording_empty_attempt = self._resource_attempt_id
            return None
        error = None
        if not self.supports_local_artifacts:
            error = "Docker creation recording is unavailable on this backend."
        elif not self._start_docker_recording(admissions):
            error = "Docker creation recording could not be prepared."
        return None if error is None else LabResult(success=False, error=error)

    def _start_docker_recording(
        self, admissions: tuple[DeploymentDockerAuthorityAdmission, ...]
    ) -> bool:
        """Start the recorder for the admissions and return True on success."""
        try:
            ownership = self._ensure_resource_ownership()
            store = RecordingStore(
                ownership,
                daemon_id=self._ownership_daemon_id(),
                attempt_id=self._resource_attempt_id,
            )
            self._recording_session = start_recording(
                store,
                Path(self._docker_socket_path),
                {
                    item.node_address: item.execution_timeout_seconds
                    for item in admissions
                },
                restart_allowed=lambda: self._recording_restart_allowed(store),
            )
            self._recording_sockets = {
                key: str(value)
                for key, value in self._recording_session.sockets.items()
            }
        except (
            OSError,
            ValueError,
            OwnershipConflictError,
            PathContainmentError,
            BackendTimeoutError,
        ):
            return False
        return True

    def _recording_restart_allowed(self, store: RecordingStore) -> bool:
        """Return True when an interrupted recording can restart without loss."""
        store.recover_responses()
        if store.pending() or store.gaps() or self._scoped_compose_container_ids():
            return False
        return all(
            self._recorded_child_absent(store, receipt)
            for receipt in store.ownership.receipts("container")
            if receipt.attempt_id == store.attempt_id
        )

    def _recorded_child_absent(
        self, store: RecordingStore, receipt: ResourceReceipt
    ) -> bool:
        """Return True when a recorded child is on this daemon and is gone."""
        return (
            receipt.daemon_id == store.daemon_id
            and self._recording_native().inspect(receipt.native_id) is None
        )

    def _recording_service_volumes(
        self, realization: DeploymentRealizationSpec
    ) -> dict[str, tuple[dict[str, object], ...]]:
        """Return the recording socket bind mount for each admitted service."""
        sockets = getattr(self, "_recording_sockets", {})
        if not sockets:
            return {}
        return {
            admission.service_name: (
                {
                    "type": "bind",
                    "source": sockets[admission.node_address],
                    "target": "/var/run/docker.sock",
                    "read_only": False,
                },
            )
            for admission in docker_authority_admissions(realization)
        }

    def _write_docker_recording_override(
        self, realization: DeploymentRealizationSpec
    ) -> Path | None:
        """Write the Compose override that mounts the recording sockets."""
        volumes = self._recording_service_volumes(realization)
        if not volumes:
            return None
        payload = {
            "services": {
                name: {"volumes": list(items)} for name, items in volumes.items()
            }
        }
        relative = Path(".aptl/realization/lilrae-docker-recording.yml")
        replace_private_nofollow(
            self._project_dir, relative, yaml.safe_dump(payload).encode()
        )
        return self._project_dir / relative

    def recorded_docker_source(self, container_name: str) -> str | None:
        """Return only a live recording endpoint bound to a verified holder."""
        ownership = self._load_resource_ownership()
        if ownership is None:
            return None
        receipts = ownership.candidates(
            container_name, kind="container", daemon_id=self._ownership_daemon_id()
        )
        for receipt in receipts:
            if receipt.managed_by == "child":
                continue
            status = _live_session_status(ownership, receipt.attempt_id)
            if status is not None:
                source = status.get("sockets", {}).get(receipt.node_address)
                return source if isinstance(source, str) else None
        return None

    def _recorded_child_is_current(
        self, receipt: ResourceReceipt, *, recovery: bool = False
    ) -> bool:
        """Verify a recorded child receipt and return True when it is live."""
        ownership = self._ensure_resource_ownership()
        attempt_id = receipt.attempt_id if recovery else self._resource_attempt_id
        store = RecordingStore(
            ownership, daemon_id=self._ownership_daemon_id(), attempt_id=attempt_id
        )
        store.verify(receipt)
        return self._recording_native().inspect(receipt.native_id) is not None

    def runtime_descendant_inventory(
        self, attempt_id: str
    ) -> RecordedInventorySnapshot:
        """Return the recorded descendant inventory for an attempt."""
        if attempt_id and getattr(self, "_recording_empty_attempt", None) == attempt_id:
            return self._empty_attempt_inventory(attempt_id)
        if not self.supports_local_artifacts:
            return RecordedInventorySnapshot((), False, _RECORDING_UNAVAILABLE)
        ownership = self._ensure_resource_ownership()
        store = RecordingStore(
            ownership, daemon_id=self._ownership_daemon_id(), attempt_id=attempt_id
        )
        native = self._recording_native()
        native.verify_daemon()
        snapshot = RecordedInventory(store, native).observe()
        return _with_owner_status(ownership, store, attempt_id, snapshot)

    def _empty_attempt_inventory(self, attempt_id: str) -> RecordedInventorySnapshot:
        """Return the inventory of an attempt that admitted no Docker authority."""
        ownership = self._load_resource_ownership()
        receipts = ownership.receipts("container") if ownership is not None else ()
        if not any(
            r.managed_by == "child" and r.attempt_id == attempt_id for r in receipts
        ):
            return RecordedInventorySnapshot()
        return RecordedInventorySnapshot((), False, _RECORDING_UNAVAILABLE)

    def _quiesce_docker_recordings(self, attempt_id: str | None = None) -> list[str]:
        """Drain the selected recording sessions and return their failures."""
        ownership = self._load_resource_ownership()
        if ownership is None:
            return []
        failures = []
        for session in existing_sessions(ownership):
            if attempt_id is None or session.store.attempt_id == attempt_id:
                failures.extend(_drain_failures(session))
        return failures

    def _recorded_child_ids(self) -> set[str]:
        """Return the native IDs of the recorded children that are still live."""
        ownership = self._load_resource_ownership()
        if ownership is None:
            return set()
        return {
            receipt.native_id
            for receipt in ownership.receipts("container")
            if receipt.managed_by == "child"
            and self._recorded_child_is_current(receipt, recovery=True)
        }

    def _finish_docker_recordings(self, attempt_id: str | None = None) -> list[str]:
        """Stop the selected recording sessions and return their failures."""
        ownership = self._load_resource_ownership()
        if ownership is None:
            return []
        failures = []
        for session in existing_sessions(ownership):
            if attempt_id is None or session.store.attempt_id == attempt_id:
                try:
                    session.shutdown()
                except OSError, ValueError, OwnershipConflictError:
                    failures.append("recording shutdown is unavailable")
        return failures

    def _remove_recorded_children(
        self, *, remove_volumes: bool, attempt_id: str | None = None
    ) -> list[str]:
        """Remove the recorded children of an attempt and return the failures."""
        from aptl.core.deployment.lilrae_native_evidence import record_cleanup

        failures = []
        ownership = self._load_resource_ownership()
        if ownership is None:
            return failures
        for receipt in ownership.receipts("container"):
            if receipt.managed_by != "child" or (
                attempt_id is not None and receipt.attempt_id != attempt_id
            ):
                continue
            try:
                if not self._recorded_child_is_current(receipt, recovery=True):
                    record_cleanup(ownership, receipt, cause="already-absent")
                    continue
                command = remove_container_command(
                    receipt.native_id, remove_volumes=remove_volumes
                )
                if self._run(command, timeout=60).returncode:
                    failures.append("failed to remove a recorded child")
                    continue
                if self._recording_native().inspect(receipt.native_id) is not None:
                    failures.append("recorded child remains after cleanup")
                else:
                    record_cleanup(ownership, receipt, cause="after-remove")
            except (
                OSError,
                ValueError,
                OwnershipConflictError,
                PathContainmentError,
                BufferError,
            ):
                failures.append("recorded child cleanup authority is unavailable")
        return failures


def _with_owner_status(
    ownership: WorkspaceOwnership,
    store: RecordingStore,
    attempt_id: str,
    snapshot: RecordedInventorySnapshot,
) -> RecordedInventorySnapshot:
    """Add an owner gap to the snapshot when its recorder stopped unexpectedly."""
    session = next(
        (
            item
            for item in existing_sessions(ownership)
            if item.store.attempt_id == attempt_id
        ),
        None,
    )
    if session is None:
        return snapshot
    status = session.status()
    closed = store._optional_read(Path("closed.json")) == {"closed": True}
    intentionally_closed = closed and all(
        child.state != "active" for child in snapshot.children
    )
    if (
        not status or not status.get("deadline_supervision")
    ) and not intentionally_closed:
        return RecordedInventorySnapshot(
            snapshot.children,
            False,
            (*snapshot.diagnostics, "recording-owner-unavailable"),
        )
    return snapshot
