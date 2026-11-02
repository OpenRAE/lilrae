"""Receipt-backed resource and residual helper cleanup for Compose backends."""

from __future__ import annotations

import subprocess
from typing import Protocol

from aptl.core.deployment._compose_ownership_override import OwnershipConflictError
from aptl.core.deployment.errors import BackendTimeoutError
from aptl.core.deployment.lilrae_native_evidence import (
    confirm_native_absence,
    record_cleanup,
)
from aptl.core.ephemeral_containers import (
    EphemeralContainer,
    remove_container_command,
    stranded_helpers_command,
)

_DOCKER_TIMEOUT = 30
_HELPER_CLEANUP_TIMEOUT = 60


class _CleanupBackend(Protocol):
    """Backend surface required by the project-container cleanup helper."""

    _project_name: str

    def _remove_owned_containers(
        self, managed_by: str, *, remove_volumes: bool = True
    ) -> list[str]:
        """Remove only freshly verified receipt-owned native container IDs."""

        ...

    def _load_resource_ownership(self) -> object | None: ...

    def _run(
        self, cmd: list[str], *, timeout: int | None = None
    ) -> subprocess.CompletedProcess: ...


class ComposeProjectCleanupMixin(object):
    """Remove receipt-owned resources and workspace-scoped residual helpers."""

    def _remove_owned_containers(
        self, managed_by: str, *, remove_volumes: bool = True
    ) -> list[str]:
        """Remove recorded containers by verified native ID."""

        try:
            ownership = self._ensure_resource_ownership()
            receipts = tuple(
                receipt
                for receipt in ownership.receipts("container")
                if receipt.managed_by == managed_by
            )
            failures = []
            for receipt in receipts:
                if receipt.daemon_id != self._ownership_daemon_id():
                    raise OwnershipConflictError("cleanup daemon identity changed")
                if not self._raw_container_inspect(receipt.native_id):
                    if not confirm_native_absence(self, receipt):
                        raise OwnershipConflictError("container absence is unverified")
                    record_cleanup(ownership, receipt, cause="already-absent")
                    continue
                native_id = self._resolve_owned_container_id(receipt.native_id)
                command = remove_container_command(
                    native_id, remove_volumes=remove_volumes
                )
                if self._run(command, timeout=60).returncode:
                    failures.append("failed to remove receipt-owned container")
                elif not confirm_native_absence(self, receipt):
                    failures.append("failed to verify receipt-owned container removal")
                else:
                    record_cleanup(ownership, receipt, cause="after-remove")
            return failures
        except OwnershipConflictError, BackendTimeoutError, OSError, ValueError, BufferError:
            return ["failed to establish container cleanup authority"]

    def _remove_owned_volumes(self) -> list[str]:
        """Remove only receipt-owned volumes that still verify on this daemon."""

        try:
            ownership = self._ensure_resource_ownership()
            failures = []
            for receipt in ownership.receipts("volume"):
                if receipt.daemon_id != self._ownership_daemon_id():
                    raise OwnershipConflictError("cleanup daemon identity changed")
                removed = False
                if self._raw_volume_inspect(receipt.native_id):
                    volume = self._resolve_owned_volume_name(receipt.native_id)
                    if self._run(
                        ["docker", "volume", "rm", volume], timeout=_DOCKER_TIMEOUT
                    ).returncode:
                        failures.append("failed to remove receipt-owned volume")
                        continue
                    removed = True
                if not confirm_native_absence(self, receipt):
                    failures.append("failed to verify receipt-owned volume removal")
                    continue
                record_cleanup(
                    ownership,
                    receipt,
                    cause="after-remove" if removed else "already-absent",
                )
                ownership.retire_deleted_volume(receipt)
            return failures
        except OwnershipConflictError, BackendTimeoutError, OSError, ValueError, BufferError:
            return ["failed to establish volume cleanup authority"]

    def _prepare_owned_cleanup(self) -> None:
        """Verify cleanup authority, allowing a provably empty new namespace."""

        ownership = self._ensure_resource_ownership()
        daemon_id = self._docker_daemon_id or self._current_docker_daemon_id()
        if daemon_id:
            self._docker_daemon_id = daemon_id
            self._verify_compose_namespace_is_owned(ownership, daemon_id)
        elif any(
            (
                self._scoped_compose_container_ids(),
                self._scoped_compose_network_ids(),
                self._scoped_compose_volume_names(),
            )
        ):
            raise OwnershipConflictError("backend daemon identity is unavailable")

    def _remove_owned_attempt_containers(
        self, attempt_id: str, *, remove_volumes: bool = False
    ) -> None:
        """Best-effort rollback of IDs recorded for one failed attempt."""

        self._quiesce_docker_recordings(attempt_id)
        ownership = self._ensure_resource_ownership()
        for receipt in ownership.receipts("container"):
            if receipt.attempt_id != attempt_id or receipt.managed_by == "child":
                continue
            try:
                native_id = self._resolve_owned_container_id(receipt.native_id)
                removed = self._run(
                    remove_container_command(native_id, remove_volumes=remove_volumes),
                    timeout=60,
                )
                if not removed.returncode and confirm_native_absence(self, receipt):
                    record_cleanup(ownership, receipt, cause="after-remove")
            except OwnershipConflictError, BackendTimeoutError, OSError, ValueError, BufferError:
                continue
        self._remove_recorded_children(
            remove_volumes=remove_volumes, attempt_id=attempt_id
        )
        self._finish_docker_recordings(attempt_id)

    def remove_generic_materializer_containers(
        self, *, remove_volumes: bool = True
    ) -> list[str]:
        """Force-remove containers realized directly by the generic materializer."""

        return [
            *self._quiesce_docker_recordings(),
            *self._remove_owned_containers("direct", remove_volumes=remove_volumes),
        ]

    def remove_project_containers(self, *, remove_volumes: bool = True) -> list[str]:
        """Force-remove residual containers carrying the Compose project identity."""

        return [
            *self._quiesce_docker_recordings(),
            *self._remove_owned_containers("compose", remove_volumes=remove_volumes),
            *self._remove_recorded_children(remove_volumes=remove_volumes),
            *self._finish_docker_recordings(),
        ]

    def _ephemeral_project(self) -> str | None:
        """Return this workspace's project if it already exists, creating nothing.

        Loading rather than ensuring ownership keeps a helper from publishing
        workspace state or fixing the start attempt's identity as a side effect.
        An unreadable ownership state scopes nothing here: minting a helper needs
        no authority, and the operations that do are the ones that report it.
        """

        try:
            ownership = self._load_resource_ownership()
        except OwnershipConflictError:
            return None
        return None if ownership is None else ownership.project_name

    def _ephemeral_container(self, role: str) -> EphemeralContainer:
        """Mint a helper scoped to this workspace's project when it has one."""

        return EphemeralContainer.for_role(role, project=self._ephemeral_project())

    def remove_stranded_helpers(self) -> list[str]:
        """Remove this project's helpers that a killed process left not running.

        A helper that had started finishes and is auto-removed; one killed
        between create and start stays ``Created`` with nothing to reap it.
        Only helpers of this workspace's project that are not running are
        selected, so an in-flight helper and every node container are safe.
        Every failure is reported, like any other teardown step, and none stops
        the remaining helpers or the steps after this one.
        """

        native_ids = self._stranded_helper_ids()
        if native_ids is None:
            return ["failed to list stranded helper containers"]
        return [
            failure
            for failure in map(self._remove_stranded_helper, native_ids)
            if failure is not None
        ]

    def _stranded_helper_ids(self) -> list[str] | None:
        """Return this project's non-running helpers, or None if unlistable.

        Unlike minting, the sweep needs the scope to be certain: a workspace it
        cannot read is a failure to report, not a workspace with nothing in it.
        """

        try:
            ownership = self._load_resource_ownership()
            listed = (
                None
                if ownership is None
                else self._run(
                    stranded_helpers_command(ownership.project_name),
                    timeout=_HELPER_CLEANUP_TIMEOUT,
                )
            )
        except OwnershipConflictError, BackendTimeoutError, OSError:
            return None
        if listed is None:
            return []
        return (
            None
            if listed.returncode != 0
            else [line.strip() for line in listed.stdout.splitlines() if line.strip()]
        )

    def _remove_stranded_helper(self, native_id: str) -> str | None:
        """Remove one stranded helper with its volumes; return a failure if not."""

        try:
            removed = self._run(
                remove_container_command(native_id), timeout=_HELPER_CLEANUP_TIMEOUT
            )
        except BackendTimeoutError, OSError:
            removed = None
        if removed is not None and removed.returncode == 0:
            return None
        return "failed to remove a stranded helper container"
