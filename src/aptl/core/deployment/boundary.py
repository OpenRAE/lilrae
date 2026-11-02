"""Typed, authority-preserving appliance boundary enforcement values."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Literal

from aptl.core.deployment._boundary_validation import (
    DIGEST_PATTERN,
    OWNER_PATTERN,
    canonical as _canonical,
    digest as _digest,
    validate_boundary_network,
    validate_egress_ports as _validate_egress_ports,
    validate_networks as _validate_networks,
    validate_owner as _validate_owner,
    validate_platform_anchors as _validate_platform_anchors,
    validate_platform_networks as _validate_platform_networks,
    validate_raes_rules as _validate_raes_rules,
    validate_seat_component_coverage,
    validate_seat_network_scope,
    validate_zone_networks as _validate_zone_networks,
)
from aptl.core.deployment.realization import DeploymentAclRealization

_BRIDGE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,14}$")


@dataclass(frozen=True)
class BoundaryNetwork:
    """One observed backend network used to bind authored references."""

    name: str
    bridge: str
    ipv4_cidr: str | None = None
    ipv6_cidr: str | None = None
    ipv4_gateway: str | None = None
    ipv6_gateway: str | None = None
    labels: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        validate_boundary_network(
            self,
            bridge_valid=_BRIDGE.fullmatch(self.bridge) is not None,
        )

    def details(self) -> dict[str, object]:
        return {
            "name": self.name,
            "bridge": self.bridge,
            "ipv4_cidr": self.ipv4_cidr,
            "ipv6_cidr": self.ipv6_cidr,
            "ipv4_gateway": self.ipv4_gateway,
            "ipv6_gateway": self.ipv6_gateway,
            "labels": [list(item) for item in self.labels],
        }


@dataclass(frozen=True)
class AcesAclOwnerBinding:
    """Observed addresses that scope one RAES ACL owner."""

    owner_address: str
    owner_resource_type: Literal["node", "network"]
    ipv4_by_network: tuple[tuple[str, str], ...] = ()
    ipv6_by_network: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.owner_address:
            raise ValueError("ACL owner address is required")
        for network, address in (*self.ipv4_by_network, *self.ipv6_by_network):
            if not network:
                raise ValueError("ACL owner network is required")
            ipaddress.ip_address(address)

    def details(self) -> dict[str, object]:
        return {
            "owner_address": self.owner_address,
            "owner_resource_type": self.owner_resource_type,
            "ipv4_by_network": [list(item) for item in self.ipv4_by_network],
            "ipv6_by_network": [list(item) for item in self.ipv6_by_network],
        }


@dataclass(frozen=True)
class BoundaryWorkload:
    """One observed platform workload and its exact network addresses."""

    identity: str
    labels: tuple[tuple[str, str], ...]
    ipv4_by_network: tuple[tuple[str, str], ...]
    ipv6_by_network: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.identity or list(self.labels) != sorted(self.labels):
            raise ValueError("invalid boundary workload identity")
        if len(dict(self.labels)) != len(self.labels):
            raise ValueError("boundary workload labels must be unique")
        if not self.ipv4_by_network and not self.ipv6_by_network:
            raise ValueError("boundary workload must have an observed address")
        for network, address in (*self.ipv4_by_network, *self.ipv6_by_network):
            if not network:
                raise ValueError("boundary workload network is required")
            ipaddress.ip_address(address)

    def details(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "labels": [list(item) for item in self.labels],
            "ipv4_by_network": [list(item) for item in self.ipv4_by_network],
            "ipv6_by_network": [list(item) for item in self.ipv6_by_network],
        }


@dataclass(frozen=True)
class AcesBoundarySpec:
    """Concrete enforcement input for the admitted RAES authority only."""

    owner: str
    networks: tuple[BoundaryNetwork, ...]
    owner_bindings: tuple[AcesAclOwnerBinding, ...]
    rules: tuple[DeploymentAclRealization, ...]

    authority: Literal["raes"] = "raes"

    def __post_init__(self) -> None:
        _validate_owner(self.owner)
        _validate_networks(self.networks)
        bindings = {item.owner_address: item for item in self.owner_bindings}
        if len(bindings) != len(self.owner_bindings):
            raise ValueError("ACL owner bindings must be unique")
        known = {network.name for network in self.networks}
        _validate_raes_rules(self.rules, bindings, known)

    @classmethod
    def empty(cls, owner: str) -> AcesBoundarySpec:
        return cls(owner=owner, networks=(), owner_bindings=(), rules=())

    def details(self) -> dict[str, object]:
        return {
            "authority": self.authority,
            "owner": self.owner,
            "networks": [item.details() for item in self.networks],
            "owner_bindings": [item.details() for item in self.owner_bindings],
            "rules": [item.details() for item in self.rules],
        }

    def canonical_json(self) -> str:
        return _canonical(self.details())

    def digest(self) -> str:
        return _digest(self.canonical_json())


@dataclass(frozen=True)
class PlatformCrossing:
    """One compiled transport crossing between platform policy anchors."""

    source: Literal["participant", "management", "egress"]
    destination: Literal["participant", "management", "egress"]
    protocol: Literal["tcp", "udp"]
    ports: tuple[int, ...]
    purpose: str

    def __post_init__(self) -> None:
        if (
            not self.ports
            or self.ports != tuple(sorted(self.ports))
            or len(self.ports) != len(set(self.ports))
            or any(not 0 < port <= 65535 for port in self.ports)
            or not self.purpose
        ):
            raise ValueError("invalid platform crossing")

    def details(self) -> dict[str, object]:
        return {
            "source": self.source,
            "destination": self.destination,
            "protocol": self.protocol,
            "ports": list(self.ports),
            "purpose": self.purpose,
        }


@dataclass(frozen=True)
class PlatformBoundarySpec:
    """Concrete enforcement input for signed platform policy only."""

    owner: str
    policy_digest: str
    networks: tuple[BoundaryNetwork, ...]
    zone_networks: tuple[
        tuple[Literal["participant", "management", "egress"], str],
        ...,
    ]
    anchors: tuple[
        tuple[Literal["participant", "management", "egress"], BoundaryWorkload],
        ...,
    ]
    crossings: tuple[PlatformCrossing, ...]
    egress_ports: tuple[int, ...]
    default_deny: Literal[True] = True
    authority: Literal["platform"] = "platform"

    def __post_init__(self) -> None:
        _validate_owner(self.owner)
        if not DIGEST_PATTERN.fullmatch(self.policy_digest):
            raise ValueError("invalid platform policy digest")
        known = _validate_platform_networks(self.networks)
        zone_networks = _validate_zone_networks(self.zone_networks, known)
        _validate_platform_anchors(self.anchors, known, zone_networks)
        _validate_egress_ports(self.egress_ports)

    def details(self) -> dict[str, object]:
        return {
            "authority": self.authority,
            "owner": self.owner,
            "policy_digest": self.policy_digest,
            "networks": [network.details() for network in self.networks],
            "zone_networks": [
                {"zone": zone, "network": network}
                for zone, network in self.zone_networks
            ],
            "anchors": [
                {"zone": zone, "workload": workload.details()}
                for zone, workload in self.anchors
            ],
            "crossings": [item.details() for item in self.crossings],
            "egress_ports": list(self.egress_ports),
            "default_deny": self.default_deny,
        }

    def canonical_json(self) -> str:
        return _canonical(self.details())

    def digest(self) -> str:
        return _digest(self.canonical_json())


@dataclass(frozen=True)
class PlatformBoundaryBootstrapSpec:
    """Deny-only policy installed before any platform anchor can run."""

    owner: str
    policy_digest: str
    networks: tuple[BoundaryNetwork, ...]
    zone_networks: tuple[
        tuple[Literal["participant", "management", "egress"], str],
        ...,
    ]
    anchors: tuple[tuple[str, BoundaryWorkload], ...] = ()
    crossings: tuple[PlatformCrossing, ...] = ()
    egress_ports: tuple[int, ...] = ()
    default_deny: Literal[True] = True
    authority: Literal["platform"] = "platform"
    bootstrap: Literal[True] = True

    def __post_init__(self) -> None:
        _validate_owner(self.owner)
        if not DIGEST_PATTERN.fullmatch(self.policy_digest):
            raise ValueError("invalid platform policy digest")
        known = _validate_platform_networks(self.networks)
        _validate_zone_networks(self.zone_networks, known)
        if self.anchors or self.crossings or self.egress_ports:
            raise ValueError("bootstrap boundary cannot grant traffic")

    def details(self) -> dict[str, object]:
        return {
            "authority": self.authority,
            "owner": self.owner,
            "policy_digest": self.policy_digest,
            "networks": [network.details() for network in self.networks],
            "zone_networks": [
                {"zone": zone, "network": network}
                for zone, network in self.zone_networks
            ],
            "anchors": [],
            "crossings": [],
            "egress_ports": [],
            "default_deny": True,
            "bootstrap": True,
        }

    def canonical_json(self) -> str:
        return _canonical(self.details())

    def digest(self) -> str:
        return _digest(self.canonical_json())


@dataclass(frozen=True)
class SeatProtectedComponent:
    """One signed protected component projected into enforcement evidence."""

    component_class: Literal[
        "management-control",
        "evidence-capture",
        "evidence-store",
        "docker-authority",
        "credentials",
    ]
    probe_identity: str
    protocol: Literal["tcp", "udp"]
    port: int
    purpose: str

    def __post_init__(self) -> None:
        if (
            not OWNER_PATTERN.fullmatch(self.probe_identity)
            or not 0 < self.port <= 65535
            or not self.purpose
        ):
            raise ValueError("invalid protected component")

    def details(self) -> dict[str, object]:
        return {
            "component_class": self.component_class,
            "probe_identity": self.probe_identity,
            "protocol": self.protocol,
            "port": self.port,
            "purpose": self.purpose,
        }


@dataclass(frozen=True)
class SeatPermittedFlow:
    """One signed exception to the range-to-guest-host deny boundary."""

    source: Literal["ordinary-range-workload"]
    destination: Literal[
        "management-control",
        "evidence-capture",
        "evidence-store",
        "docker-authority",
        "credentials",
    ]
    protocol: Literal["tcp", "udp"]
    ports: tuple[int, ...]
    purpose: str
    probe_identity: str

    def __post_init__(self) -> None:
        if (
            not self.ports
            or len(self.ports) != len(set(self.ports))
            or any(not 0 < port <= 65535 for port in self.ports)
            or not self.purpose
            or not OWNER_PATTERN.fullmatch(self.probe_identity)
        ):
            raise ValueError("invalid protected-seat permitted flow")

    def details(self) -> dict[str, object]:
        return {
            "source": self.source,
            "destination": self.destination,
            "protocol": self.protocol,
            "ports": list(self.ports),
            "purpose": self.purpose,
            "probe_identity": self.probe_identity,
        }


@dataclass(frozen=True)
class SeatProtectionBoundarySpec:
    """Input-only default deny from all admitted range bridges to the guest."""

    owner: str
    policy_digest: str
    networks: tuple[BoundaryNetwork, ...]
    protected_components: tuple[SeatProtectedComponent, ...]
    permitted_flows: tuple[SeatPermittedFlow, ...]
    default_deny: Literal[True] = True
    authority: Literal["seat-protection"] = "seat-protection"

    def __post_init__(self) -> None:
        _validate_owner(self.owner)
        if not DIGEST_PATTERN.fullmatch(self.policy_digest):
            raise ValueError("invalid protected-seat policy digest")
        validate_seat_network_scope(self.networks)
        validate_seat_component_coverage(
            self.protected_components, self.permitted_flows
        )

    def details(self) -> dict[str, object]:
        return {
            "authority": self.authority,
            "owner": self.owner,
            "policy_digest": self.policy_digest,
            "networks": [item.details() for item in self.networks],
            "protected_components": [
                item.details() for item in self.protected_components
            ],
            "permitted_flows": [item.details() for item in self.permitted_flows],
            "default_deny": self.default_deny,
        }

    def canonical_json(self) -> str:
        return _canonical(self.details())

    def digest(self) -> str:
        return _digest(self.canonical_json())


BoundaryEnforcementSpec = (
    AcesBoundarySpec
    | PlatformBoundarySpec
    | PlatformBoundaryBootstrapSpec
    | SeatProtectionBoundarySpec
)
