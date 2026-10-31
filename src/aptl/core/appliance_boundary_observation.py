"""Strict normalized observations used for appliance-boundary qualification."""

from __future__ import annotations

import ipaddress
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aptl.core.appliance_boundary import Digest


class _StrictObservation(BaseModel):
    """Base for immutable, closed boundary-observation records."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class BoundaryEndpoint(_StrictObservation):
    """One physical-host endpoint attributed to an approved audience."""

    audience: Literal["participant", "recovery", "host-mcp"]
    address: str
    port: int = Field(ge=1, le=65535)
    protocol: Literal["tcp", "udp"]
    guest_address: str | None = None
    guest_port: int | None = Field(default=None, ge=1, le=65535)

    @model_validator(mode="after")
    def validate_mapping(self) -> Self:
        """Require a complete guest endpoint for mapped host listeners."""

        if (self.guest_address is None) != (self.guest_port is None):
            raise ValueError("guest mapping requires both address and port")
        for address in (self.address, self.guest_address):
            if address is not None and not ipaddress.ip_address(address).is_loopback:
                raise ValueError("boundary endpoints must bind loopback")
        if self.audience == "host-mcp" and self.guest_port is None:
            raise ValueError("host MCP requires an explicit guest endpoint mapping")
        return self


class HostBoundaryObservation(_StrictObservation):
    """Authenticated outer observation produced by the #824 adapter."""

    observation_id: str = Field(min_length=1, max_length=128)
    policy_digest: Digest
    payload_digest: Digest
    boot_id: str = Field(min_length=1, max_length=128)
    complete: bool
    listeners: tuple[BoundaryEndpoint, ...]
    forbidden_reachability_passed: bool


class BoundaryEnforcementObservation(_StrictObservation):
    """Kernel readback evidence for one independent policy authority."""

    authority: Literal["raes", "platform", "seat-protection"]
    source_digest: Digest
    enforcement_digest: Digest
    families: tuple[Literal["bridge", "inet"], ...]
    default_deny_observed: bool
    network_coverage: tuple[str, ...] = ()


class BoundaryProbeObservation(_StrictObservation):
    """One positive or negative reachability proof."""

    identity: str = Field(min_length=1, max_length=512)
    authority: Literal["raes", "platform", "seat-protection"]
    source: str = Field(min_length=1, max_length=160)
    destination: str = Field(min_length=1, max_length=160)
    protocol: Literal["any", "tcp", "udp", "icmp"]
    port: int | None = Field(default=None, ge=1, le=65535)
    expectation: Literal["reachable", "blocked"]
    source_network: str | None = Field(default=None, min_length=1, max_length=128)
    address_family: Literal["ipv4", "ipv6"] | None = None
    target_ready: bool = True
    passed: bool

    @model_validator(mode="after")
    def validate_transport_port(self) -> BoundaryProbeObservation:
        """Require ports only for TCP and UDP boundary probes."""

        if (self.protocol in {"tcp", "udp"}) != (self.port is not None):
            raise ValueError("probe port must match its transport")
        return self


class DockerAuthorityHolder(_StrictObservation):
    """Observed guest-daemon authority held by one workload."""

    identity: str = Field(min_length=1, max_length=128)
    label_selector: str = Field(min_length=1, max_length=160)
    daemon_id: str = Field(min_length=1, max_length=128)
    access: Literal["socket", "api"]
    privileged: bool
    host_pid_namespace: bool
    host_network_namespace: bool
    device_count: int = Field(ge=0)
    admitted: bool = False


class RangeWorkloadObservation(_StrictObservation):
    """Bounded effective posture for one ordinary receipt-owned workload."""

    identity: str = Field(min_length=1, max_length=128)
    networks: tuple[str, ...]
    receipt_bound: bool
    inspect_complete: bool
    privileged: bool
    host_pid_namespace: bool
    host_network_namespace: bool
    device_count: int = Field(ge=0)
    unapproved_docker_authority: bool
    protected_mount: bool
    credential_exposure: bool


class GuestBoundaryObservation(_StrictObservation):
    """Normalized selected-daemon and kernel observation."""

    policy_digest: Digest
    raes_plan_digest: Digest
    raes_boundary_required: bool = False
    boot_id: str = Field(min_length=1, max_length=128)
    guest_daemon_id: str = Field(min_length=1, max_length=128)
    workbench_policy_version: str = Field(min_length=1, max_length=128)
    enforcements: tuple[BoundaryEnforcementObservation, ...]
    observation_complete: bool
    probes: tuple[BoundaryProbeObservation, ...]
    docker_authority_holders: tuple[DockerAuthorityHolder, ...]
    range_workloads: tuple[RangeWorkloadObservation, ...] = ()
