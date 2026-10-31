"""Shared validation and canonicalization for boundary enforcement values."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aptl.core.deployment.boundary import (
        AcesAclOwnerBinding,
        BoundaryNetwork,
        BoundaryWorkload,
    )
    from aptl.core.deployment.realization import DeploymentAclRealization

OWNER_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")
DIGEST_PATTERN = re.compile(r"sha256:[a-f0-9]{64}")
_PLATFORM_ZONES = {"participant", "management", "egress"}


def validate_owner(owner: str) -> None:
    """Require a bounded project/seat ownership token."""

    if not OWNER_PATTERN.fullmatch(owner):
        raise ValueError("invalid boundary owner")


def validate_boundary_network(
    network: BoundaryNetwork,
    *,
    bridge_valid: bool,
) -> None:
    """Validate one observed network without loading backend-specific state."""

    if not network.name or not bridge_valid:
        raise ValueError("invalid boundary network")
    for cidr in (network.ipv4_cidr, network.ipv6_cidr):
        if cidr is not None:
            ipaddress.ip_network(cidr, strict=False)
    _validate_gateway(network.ipv4_gateway, network.ipv4_cidr, 4)
    _validate_gateway(network.ipv6_gateway, network.ipv6_cidr, 6)
    if list(network.labels) != sorted(network.labels) or len(
        dict(network.labels)
    ) != len(network.labels):
        raise ValueError("boundary network labels must be unique and sorted")


def _validate_gateway(gateway: str | None, cidr: str | None, version: int) -> None:
    """Require an observed gateway to belong to its matching subnet."""

    if gateway is None:
        return
    parsed = ipaddress.ip_address(gateway)
    if (
        parsed.version != version
        or cidr is None
        or parsed not in ipaddress.ip_network(cidr, strict=False)
    ):
        raise ValueError("boundary network gateway is outside its subnet")


def validate_networks(networks: tuple[BoundaryNetwork, ...]) -> None:
    """Require unique concrete network and bridge identities."""

    names = [network.name for network in networks]
    bridges = [network.bridge for network in networks]
    if len(names) != len(set(names)) or len(bridges) != len(set(bridges)):
        raise ValueError("boundary networks must have unique names and bridges")


def canonical(details: dict[str, object]) -> str:
    """Serialize enforcement input deterministically for hashing and transport."""

    return json.dumps(details, sort_keys=True, separators=(",", ":"))


def digest(payload: str) -> str:
    """Return the lowercase SHA-256 identity of canonical policy text."""

    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def validate_raes_rules(
    rules: tuple[DeploymentAclRealization, ...],
    bindings: dict[str, AcesAclOwnerBinding],
    known_networks: set[str],
) -> None:
    """Require exact owner bindings, known endpoints, and deterministic order."""

    prior: tuple[str, int, str] | None = None
    for rule in rules:
        binding = bindings.get(rule.owner_address)
        if binding is None or binding.owner_resource_type != rule.owner_resource_type:
            raise ValueError("ACL rule has no exact owner binding")
        endpoints = (rule.from_network, rule.to_network)
        if any(item is not None and item not in known_networks for item in endpoints):
            raise ValueError("ACL rule references an unknown network")
        current = (rule.owner_address, rule.order, rule.name)
        if prior is not None and current < prior:
            raise ValueError("ACL rules must have deterministic owner order")
        prior = current


def validate_platform_networks(
    networks: tuple[BoundaryNetwork, ...],
) -> set[str]:
    """Require exactly three distinct IPv4-only platform policy domains."""

    validate_networks(networks)
    if len(networks) != 3 or any(network.ipv6_cidr is not None for network in networks):
        raise ValueError("platform networks must be three IPv4 policy domains")
    return {network.name for network in networks}


def validate_zone_networks(
    entries: tuple[tuple[Any, str], ...],
    known_networks: set[str],
) -> dict[str, str]:
    """Require an exact one-to-one mapping from zones to platform networks."""

    zone_networks = dict(entries)
    if (
        set(zone_networks) != _PLATFORM_ZONES
        or len(entries) != 3
        or set(zone_networks.values()) != known_networks
    ):
        raise ValueError("platform zone networks must be exact and distinct")
    return zone_networks


def validate_platform_anchors(
    anchors: tuple[tuple[Any, BoundaryWorkload], ...],
    known_networks: set[str],
    zone_networks: dict[str, str],
) -> None:
    """Require one IPv4 anchor per zone on only signed platform networks."""

    zones = [zone for zone, _workload in anchors]
    if set(zones) != _PLATFORM_ZONES or len(zones) != 3:
        raise ValueError("platform anchors must cover each policy zone")
    for zone, workload in anchors:
        attached = (*workload.ipv4_by_network, *workload.ipv6_by_network)
        if any(network not in known_networks for network, _address in attached):
            raise ValueError("platform workload references an unknown network")
        ipv4_networks = {network for network, _address in workload.ipv4_by_network}
        if (
            not ipv4_networks
            or workload.ipv6_by_network
            or zone_networks[zone] not in ipv4_networks
        ):
            raise ValueError("platform workload requires its IPv4 policy attachment")


def validate_egress_ports(ports: tuple[int, ...]) -> None:
    """Require unique, valid external TCP port numbers."""

    if len(ports) != len(set(ports)) or any(not 0 < port <= 65535 for port in ports):
        raise ValueError("invalid platform egress ports")


def validate_seat_network_scope(networks: tuple[BoundaryNetwork, ...]) -> None:
    """Require address families and gateways for every protected range bridge."""

    validate_networks(networks)
    if not networks or any(
        network.ipv4_cidr is None and network.ipv6_cidr is None for network in networks
    ):
        raise ValueError("protected-seat networks require observed address families")
    if any(
        (network.ipv4_cidr is not None and network.ipv4_gateway is None)
        or (network.ipv6_cidr is not None and network.ipv6_gateway is None)
        for network in networks
    ):
        raise ValueError("protected-seat networks require observed gateways")


def validate_seat_component_coverage(
    protected_components: tuple[Any, ...], permitted_flows: tuple[Any, ...]
) -> None:
    """Require exact protected classes and unique active probe identities."""

    required_classes = {
        "management-control",
        "evidence-capture",
        "evidence-store",
        "docker-authority",
        "credentials",
    }
    classes = [item.component_class for item in protected_components]
    probes = [item.probe_identity for item in (*protected_components, *permitted_flows)]
    if (
        set(classes) != required_classes
        or len(classes) != len(required_classes)
        or len(probes) != len(set(probes))
    ):
        raise ValueError(
            "protected-seat component coverage must be complete and unique"
        )
