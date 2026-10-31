"""Docker Compose network realization helpers."""

from __future__ import annotations

from typing import Any

from aptl.core.deployment._compose_network_operations import (
    _DEFAULT_BRIDGE_NETWORK,
)
from aptl.core.deployment._compose_network_conflicts import (
    _network_subnet_conflicts,
    _planned_networks_to_create,
)
from aptl.core.deployment._compose_node_topology import (
    dynamic_ip_range as _dynamic_ip_range,
    pinned_addresses_by_network as _pinned_addresses_by_network,
)
from aptl.core.deployment._compose_realization_networks import (
    _compose_network_key,
    _concrete_network_name,
    _container_network_ip,
    _container_networks,
    _inspect_past_restart,
    _match_managed_network,
    _network_policy_mismatches,
    _node_network_aliases,
    _node_network_attachments,
    _resolve_realization_network_attachments,
    _realized_attachment_failures,
)
from aptl.core.deployment._compose_resource_ownership import (
    OwnershipConflictError,
)
from aptl.core.deployment.realization import (
    DeploymentNetworkAttachment,
    DeploymentNetworkRealization,
    DeploymentRealizationSpec,
)
from aptl.core.lab_types import LabResult



class ComposeRealizationNetworkMixin:
    """Realize typed scenario networks through Docker Compose."""

    def _reconcile_declared_networks(
        self, realization: DeploymentRealizationSpec
    ) -> LabResult | None:
        """Require the same topology readback for every SDL startup route."""

        if not realization.networks:
            return None
        failures = self._reconcile_realization_networks(realization)
        return (
            LabResult(success=False, error="; ".join(failures[:5]))
            if failures
            else None
        )

    def _ensure_realization_networks(
        self,
        realization: DeploymentRealizationSpec,
    ) -> list[str]:
        """Create scenario-declared project networks that do not exist."""

        if not realization.networks:
            return []
        managed_networks = set(self.host_list_lab_networks(self._project_name))
        conflicts = self._realization_network_subnet_conflicts(
            realization,
            managed_networks,
        )
        if conflicts:
            return conflicts
        # Confine each network's dynamic allocation pool off the statically
        # pinned node addresses, the SAME split the generated compose file uses
        # (_render_networks). Docker ignores the compose ip_range when APTL has
        # already created the network, so it must be applied at creation here or
        # a dynamically-placed node seizes a pinned address and the pinned
        # container fails with "Address already in use" (issue #875).
        pinned = _pinned_addresses_by_network(realization)
        failures: list[str] = []
        for network in realization.networks:
            match = _match_managed_network(
                network.name,
                managed_networks,
                self._project_name,
            )
            if match is not None:
                failures.extend(
                    self._realization_network_reuse_failures(match, network)
                )
                continue
            ip_range = (
                _dynamic_ip_range(
                    network.cidr, network.gateway, pinned.get(network.name, set())
                )
                if network.cidr
                else None
            )
            result = self.create_network(network, ip_range=ip_range)
            if result.success:
                managed_networks.add(
                    _concrete_network_name(network.name, self._project_name)
                )
            else:
                failures.append(
                    result.error or f"Failed to create realized network {network.name}."
                )
        return failures

    def _realization_network_subnet_conflicts(
        self,
        realization: DeploymentRealizationSpec,
        managed_networks: set[str],
    ) -> list[str]:
        """Return preflight failures for Docker subnet overlaps."""

        planned_networks = _planned_networks_to_create(
            realization,
            managed_networks,
            self._project_name,
        )
        if not planned_networks:
            return []
        existing_networks = self._host_network_inspection_details()
        if not existing_networks:
            return []
        return [
            failure
            for network in planned_networks
            for failure in _network_subnet_conflicts(network, existing_networks)
        ]

    def _host_network_inspection_details(self) -> list[dict[str, Any]]:
        """Return inspectable Docker network details for overlap checks."""

        return [
            details
            for name in self.host_list_networks()
            if (details := self.host_inspect_network(name))
        ]

    def _realization_network_reuse_failures(
        self,
        network_name: str,
        network: DeploymentNetworkRealization,
    ) -> list[str]:
        """Return fail-closed errors for an existing realized network."""

        failures: list[str] = []
        native_id = ""
        try:
            # Keep the verified handle: inspecting by the mutable name again
            # would let a same-name replacement between the two calls redirect
            # verification onto a different network (issue #1105).
            native_id = self._resolve_owned_network_id(network_name)
        except OwnershipConflictError:
            failures = [
                f"Existing network {network_name} has no verified APTL ownership receipt."
            ]
        compose_key = _compose_network_key(network.name) if not failures else None
        if not failures and not compose_key:
            failures = ["Invalid network realization name."]
        details = self.host_inspect_network(native_id) if not failures else {}
        if not failures and not details:
            failures = [
                f"Existing network {network_name} was not inspectable "
                f"for realized network {network.name}."
            ]
        if not failures:
            labels = details.get("labels")
            labels = labels if isinstance(labels, dict) else {}
            failures = [
                f"Existing network {network_name} does not match realized "
                f"network {network.name}: {mismatch}."
                for mismatch in _network_policy_mismatches(
                    details,
                    labels,
                    network,
                    project_name=self._project_name,
                    compose_key=str(compose_key),
                )
            ]
        return failures

    def _reconcile_realization_networks(
        self,
        realization: DeploymentRealizationSpec,
    ) -> list[str]:
        """Align realized containers with the scenario-declared networks."""

        managed_networks = set(self.host_list_lab_networks(self._project_name))
        if not managed_networks:
            return ["APTL managed networks were not visible after startup."]

        failures: list[str] = []
        for node in realization.nodes:
            attachments = _node_network_attachments(node)
            if not node.container_name or not attachments:
                continue
            desired, missing = _resolve_realization_network_attachments(
                attachments,
                managed_networks,
                self._project_name,
            )
            if missing:
                failures.append(
                    "No managed Docker network matched RAES network(s) "
                    f"{', '.join(missing)} for node {node.name}."
                )
                continue
            info = _inspect_past_restart(self.container_inspect, node.container_name)
            if not info:
                failures.append(
                    f"Container {node.container_name} was not inspectable "
                    f"for realized node {node.name}."
                )
                continue
            current = _container_networks(info) & managed_networks
            aliases = _node_network_aliases(node)
            reattach, reattach_failures = self._reconnect_static_ip_drifts(
                node.container_name,
                info,
                desired,
                aliases=aliases,
            )
            node_failures = list(reattach_failures)
            current = current - set(reattach)
            node_failures.extend(
                self._disconnect_extra_networks(
                    node.container_name,
                    current,
                    set(desired),
                )
            )
            node_failures.extend(
                self._connect_missing_networks(
                    node.container_name,
                    current,
                    desired,
                    aliases,
                )
            )
            if not node_failures:
                node_failures = _realized_attachment_failures(
                    node.name,
                    _inspect_past_restart(self.container_inspect, node.container_name),
                    desired,
                    aliases,
                    managed_networks,
                )
            if node_failures:
                failures.extend(node_failures)
                continue
            failures.extend(
                self._disconnect_default_bridge(
                    node.container_name,
                    info,
                    desired,
                    keep_for_published_port=bool(node.published_ports),
                )
            )
        return failures

    def _disconnect_default_bridge(
        self,
        container_name: str,
        info: dict[str, Any],
        desired: dict[str, DeploymentNetworkAttachment],
        *,
        keep_for_published_port: bool = False,
    ) -> list[str]:
        """Detach a node's implicit default-bridge attachment, if any.

        Runs after the declared networks are connected, so a generic-
        materializer node keeps outbound connectivity (e.g. for its own
        package installs, which run before this reconciliation step) right
        up until its real attachments are in place.
        """

        if (
            keep_for_published_port
            or _DEFAULT_BRIDGE_NETWORK not in _container_networks(info)
            or _DEFAULT_BRIDGE_NETWORK in desired
        ):
            return []
        result = self.disconnect_container_network(
            container_name, _DEFAULT_BRIDGE_NETWORK
        )
        if not result.success:
            return [
                result.error
                or f"Failed to disconnect {container_name} from "
                f"{_DEFAULT_BRIDGE_NETWORK}."
            ]
        observed = self.container_inspect(container_name)
        failures: list[str] = []
        if not observed or _DEFAULT_BRIDGE_NETWORK in _container_networks(observed):
            failures.append(
                f"Container {container_name}: removal of the default bridge "
                "was not observed."
            )
        return failures

    def _reconnect_static_ip_drifts(
        self,
        container_name: str,
        info: dict[str, Any],
        desired: dict[str, DeploymentNetworkAttachment],
        *,
        aliases: tuple[str, ...] = (),
    ) -> tuple[list[str], list[str]]:
        """Reconnect endpoints missing their declared IP or service DNS aliases."""

        reattach: list[str] = []
        failures: list[str] = []
        for network_name, attachment in desired.items():
            endpoint = (
                info.get("NetworkSettings", {}).get("Networks", {}).get(network_name)
            )
            if not isinstance(endpoint, dict):
                continue
            current_ip = _container_network_ip(info, network_name)
            ip_drift = bool(
                attachment.ipv4_address and current_ip != attachment.ipv4_address
            )
            alias_drift = not set(aliases).issubset(endpoint.get("Aliases") or ())
            if ip_drift or alias_drift:
                result = self.disconnect_container_network(container_name, network_name)
                if result.success:
                    reattach.append(network_name)
                else:
                    failures.append(
                        result.error
                        or (
                            f"Failed to disconnect {container_name} "
                            f"from {network_name}."
                        )
                    )
        return reattach, failures

    def _disconnect_extra_networks(
        self,
        container_name: str,
        current: set[str],
        desired: set[str],
    ) -> list[str]:
        """Detach a realized container from project networks outside its spec."""

        failures: list[str] = []
        for network_name in sorted(current - desired):
            result = self.disconnect_container_network(container_name, network_name)
            if not result.success:
                failures.append(
                    result.error
                    or f"Failed to disconnect {container_name} from {network_name}."
                )
        return failures

    def _connect_missing_networks(
        self,
        container_name: str,
        current: set[str],
        desired: dict[str, DeploymentNetworkAttachment],
        aliases: tuple[str, ...],
    ) -> list[str]:
        """Attach a realized container to declared project networks it lacks."""

        failures: list[str] = []
        for network_name in sorted(set(desired) - current):
            attachment = desired[network_name]
            result = self.connect_container_network(
                container_name,
                network_name,
                ipv4_address=attachment.ipv4_address,
                aliases=aliases,
            )
            if not result.success:
                failures.append(
                    result.error
                    or f"Failed to connect {container_name} to {network_name}."
                )
        return failures
