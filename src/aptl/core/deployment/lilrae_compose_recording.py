"""Native creation recording integrated with the existing Compose lifecycle."""

from __future__ import annotations

from pathlib import Path

import yaml

from aptl.core.deployment._compose_resource_ownership import (
    OwnershipConflictError,
    ResourceReceipt,
)
from aptl.core.deployment._compose_runtime_orchestration import (
    docker_authority_admissions,
)
from aptl.core.deployment.lilrae_docker_http import NativeDocker
from aptl.core.deployment.lilrae_docker_recorder import (
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


class ComposeDockerRecordingMixin:
    def native_evidence_artifacts(self, attempt_id):
        """Expose producer bytes without granting a collector native access."""
        from aptl.core.deployment.lilrae_native_evidence import (
            native_evidence_artifacts,
        )

        ownership = self._load_resource_ownership()
        if ownership is None or not self._docker_daemon_id:
            raise OwnershipConflictError("native evidence owner is unavailable")
        return native_evidence_artifacts(ownership, attempt_id, self._docker_daemon_id)

    def _recording_native(self) -> NativeDocker:
        socket_path = self._docker_socket_path
        if not socket_path:
            raise OwnershipConflictError("recording daemon endpoint is not bound")
        return NativeDocker(
            socket_path,
            self._ownership_daemon_id(),
            identity=self._docker_socket_identity,
        )

    def _prepare_docker_recording(self, realization) -> LabResult | None:
        admissions = docker_authority_admissions(realization)
        self._recording_empty_attempt = None
        if not admissions:
            self._recording_empty_attempt = self._resource_attempt_id
            return None
        if not self.supports_local_artifacts:
            return LabResult(
                success=False,
                error="Docker creation recording is unavailable on this backend.",
            )
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
            return LabResult(
                success=False, error="Docker creation recording could not be prepared."
            )
        return None

    def _recording_restart_allowed(self, store: RecordingStore) -> bool:
        store.recover_responses()
        if store.pending() or store.gaps() or self._scoped_compose_container_ids():
            return False
        for receipt in store.ownership.receipts("container"):
            if receipt.attempt_id != store.attempt_id:
                continue
            if receipt.daemon_id != store.daemon_id:
                return False
            if self._recording_native().inspect(receipt.native_id) is not None:
                return False
        return True

    def _recording_service_volumes(self, realization) -> dict[str, tuple[dict, ...]]:
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

    def _write_docker_recording_override(self, realization) -> Path | None:
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
            for session in existing_sessions(ownership):
                if session.store.attempt_id == receipt.attempt_id:
                    status = session.status()
                    if status is not None:
                        source = status.get("sockets", {}).get(receipt.node_address)
                        return source if isinstance(source, str) else None
        return None

    def _recorded_child_is_current(
        self, receipt: ResourceReceipt, *, recovery: bool = False
    ) -> bool:
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
        if attempt_id and getattr(self, "_recording_empty_attempt", None) == attempt_id:
            ownership = self._load_resource_ownership()
            receipts = ownership.receipts("container") if ownership is not None else ()
            if not any(
                r.managed_by == "child" and r.attempt_id == attempt_id for r in receipts
            ):
                return RecordedInventorySnapshot()
            return RecordedInventorySnapshot(
                (), False, ("native-recording-unavailable",)
            )
        if not self.supports_local_artifacts:
            return RecordedInventorySnapshot(
                (), False, ("native-recording-unavailable",)
            )
        ownership = self._ensure_resource_ownership()
        store = RecordingStore(
            ownership, daemon_id=self._ownership_daemon_id(), attempt_id=attempt_id
        )
        native = self._recording_native()
        native.verify_daemon()
        snapshot = RecordedInventory(store, native).observe()
        sessions = tuple(
            session
            for session in existing_sessions(ownership)
            if session.store.attempt_id == attempt_id
        )
        if sessions:
            status = sessions[0].status()
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

    def _quiesce_docker_recordings(self, attempt_id: str | None = None) -> list[str]:
        ownership = self._load_resource_ownership()
        if ownership is None:
            return []
        failures = []
        for session in existing_sessions(ownership):
            if attempt_id is None or session.store.attempt_id == attempt_id:
                try:
                    if session.status() is not None:
                        failures.extend(session.quiesce())
                    session.store.recover_responses()
                    if session.store.pending():
                        failures.append(
                            "a recorded Docker create has an unresolved native outcome"
                        )
                    if session.store.gaps():
                        failures.append(
                            "Docker descendant recording has unresolved coverage gaps"
                        )
                except (
                    OSError,
                    ValueError,
                    OwnershipConflictError,
                    PathContainmentError,
                ):
                    failures.append("recorded Docker creation drain is unavailable")
        return failures

    def _recorded_child_ids(self) -> set[str]:
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
            except OSError, ValueError, OwnershipConflictError, PathContainmentError, BufferError:
                failures.append("recorded child cleanup authority is unavailable")
        return failures
