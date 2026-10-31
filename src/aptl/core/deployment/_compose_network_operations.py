"""Docker network create, connect, disconnect, and cleanup operations."""

from __future__ import annotations

from aptl.core.deployment._compose_resource_ownership import (
    OwnershipConflictError,
)
from aptl.core.deployment.errors import BackendTimeoutError
from aptl.core.deployment.realization import DeploymentNetworkRealization
from aptl.core.lab_types import LabResult

_REALIZATION_TIMEOUT = 30

# Docker's fixed built-in default network. `docker run` with no `--network`
# flag (the generic materializer's node creation, ADR-048) implicitly attaches
# it; Compose-started containers never do. It is disconnected explicitly
# rather than folded into "unmanaged" cleanup, which deliberately never
# touches a network APTL did not create (issue #581) - "bridge" is the one
# accidental attachment, not a user's own network APTL should leave alone.
_DEFAULT_BRIDGE_NETWORK = "bridge"


class ComposeNetworkOperationsMixin:
    """Run native Docker network operations on receipt-owned resources."""

    def create_network(
        self,
        network: DeploymentNetworkRealization,
        ip_range: str | None = None,
    ) -> LabResult:
        """Create one project-scoped Docker bridge network.

        ``ip_range`` confines dynamic address allocation to a sub-range so
        statically-pinned node addresses stay collision-free; it must be applied
        at creation because Docker ignores the compose file's ip_range once the
        network already exists (issue #875).
        """

        self._ensure_resource_ownership()
        attempt_id = self._resource_attempt_id
        outcome: LabResult
        if attempt_id is None:
            outcome = LabResult(
                success=False, error="Backend attempt identity is unavailable."
            )
        else:
            outcome = self._create_attempt_network(
                network, attempt_id=attempt_id, ip_range=ip_range
            )
        return outcome

    def connect_container_network(
        self,
        container_name: str,
        network_name: str,
        *,
        ipv4_address: str | None = None,
        aliases: tuple[str, ...] = (),
    ) -> LabResult:
        """Connect one container to one Docker network."""

        native_id = self._resolve_owned_container_id(container_name)
        network_id = self._resolve_owned_network_id(network_name)
        cmd = ["docker", "network", "connect"]
        if ipv4_address:
            cmd.extend(["--ip", ipv4_address])
        for alias in dict.fromkeys(alias for alias in aliases if alias):
            cmd.extend(["--alias", alias])
        cmd.extend([network_id, native_id])
        result = self._run(cmd, timeout=_REALIZATION_TIMEOUT)
        if result.returncode != 0:
            return LabResult(
                success=False,
                error=(
                    f"Failed to connect {container_name} to {network_name}: "
                    f"{result.stderr.strip()}"
                ),
            )
        return LabResult(success=True, message="connected")

    def disconnect_container_network(
        self,
        container_name: str,
        network_name: str,
    ) -> LabResult:
        """Disconnect one container from one Docker network."""

        network_id = (
            _DEFAULT_BRIDGE_NETWORK
            if network_name == _DEFAULT_BRIDGE_NETWORK
            else self._resolve_owned_network_id(network_name)
        )
        result = self._run(
            [
                "docker",
                "network",
                "disconnect",
                network_id,
                self._resolve_owned_container_id(container_name),
            ],
            timeout=_REALIZATION_TIMEOUT,
        )
        if result.returncode != 0:
            return LabResult(
                success=False,
                error=(
                    f"Failed to disconnect {container_name} from {network_name}: "
                    f"{result.stderr.strip()}"
                ),
            )
        return LabResult(success=True, message="disconnected")

    def remove_project_networks(self) -> list[str]:
        """Remove only freshly verified receipt-owned networks."""

        from aptl.core.deployment.lilrae_native_evidence import (
            confirm_native_absence,
            record_cleanup,
        )

        failures: list[str] = []
        try:
            ownership = self._ensure_resource_ownership()
            for receipt in ownership.receipts("network"):
                if receipt.daemon_id != self._ownership_daemon_id():
                    raise OwnershipConflictError("cleanup daemon identity changed")
                if not self.host_inspect_network(receipt.native_id):
                    if not confirm_native_absence(self, receipt):
                        raise OwnershipConflictError("network absence is unverified")
                    record_cleanup(ownership, receipt, cause="already-absent")
                    continue
                network_id = self._resolve_owned_network_id(receipt.native_id)
                result = self._run(
                    ["docker", "network", "rm", network_id],
                    timeout=_REALIZATION_TIMEOUT,
                )
                if result.returncode != 0:
                    failures.append("Failed to remove a receipt-owned network")
                elif not confirm_native_absence(self, receipt):
                    failures.append("Failed to verify receipt-owned network removal")
                else:
                    record_cleanup(ownership, receipt, cause="after-remove")
        except (
            BackendTimeoutError,
            OwnershipConflictError,
            OSError,
            ValueError,
            BufferError,
        ):
            failures.append("Failed to establish network cleanup authority")
        return failures
