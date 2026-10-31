"""Fresh fatal appliance-boundary inventory and verdict."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aptl.core.appliance_boundary import (
    ApplianceBoundaryBinding,
    ApplianceBoundaryPolicy,
    Digest,
)
from aptl.utils.redaction import redact

_INCOMPLETE_ENFORCEMENT = "boundary.guest-enforcement-incomplete"


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


@dataclass(frozen=True)
class BoundaryQualificationResult:
    """Fatal boundary verdict plus its redacted evidence inventory."""

    passed: bool
    findings: tuple[str, ...]
    inventory: dict[str, object]


def qualify_appliance_boundary(
    policy: ApplianceBoundaryPolicy,
    binding: ApplianceBoundaryBinding,
    host: HostBoundaryObservation | None,
    guest: GuestBoundaryObservation,
    *,
    phase: Literal["image-qualification", "start"] = "start",
) -> BoundaryQualificationResult:
    """Compare both trust domains and return bounded redacted evidence."""

    findings: list[str] = []
    if host is None:
        findings.append("boundary.host-observation-missing")
    else:
        _append_host_findings(policy, binding, host, findings)
    _append_guest_findings(policy, binding, guest, findings)
    inventory = _inventory(policy, binding, host, guest, findings, phase)
    return BoundaryQualificationResult(
        passed=not findings,
        findings=tuple(findings),
        inventory=redact(inventory),
    )


def _append_host_findings(
    policy: ApplianceBoundaryPolicy,
    binding: ApplianceBoundaryBinding,
    host: HostBoundaryObservation,
    findings: list[str],
) -> None:
    """Compare fresh outer-host evidence with the signed binding."""

    if policy.host_mcp_contract is not None:
        from aptl.appliance.seat.observation import observation_id_for

        if host.observation_id != observation_id_for(host):
            findings.append("boundary.host-observation-content-mismatch")
    comparisons = (
        (
            host.observation_id != binding.host_observation_id,
            "boundary.host-observation-identity-mismatch",
        ),
        (
            host.policy_digest != binding.policy_digest,
            "boundary.host-policy-digest-mismatch",
        ),
        (
            host.payload_digest != binding.payload_digest,
            "boundary.host-payload-digest-mismatch",
        ),
        (
            host.boot_id != (binding.host_boot_id or binding.boot_id),
            "boundary.host-boot-identity-mismatch",
        ),
    )
    findings.extend(reason for mismatch, reason in comparisons if mismatch)
    if not host.complete:
        findings.append("boundary.host-observation-incomplete")
    if not host.forbidden_reachability_passed:
        findings.append("boundary.host-forbidden-reachability")
    _append_host_listener_findings(policy, host, findings)


def _append_guest_findings(
    policy: ApplianceBoundaryPolicy,
    binding: ApplianceBoundaryBinding,
    guest: GuestBoundaryObservation,
    findings: list[str],
) -> None:
    """Compare guest policy, daemon, enforcement, and authority evidence."""

    comparisons = (
        (
            guest.policy_digest != binding.policy_digest,
            "boundary.guest-policy-digest-mismatch",
        ),
        (
            guest.raes_plan_digest != binding.raes_plan_digest,
            "boundary.guest-raes-plan-digest-mismatch",
        ),
        (
            guest.raes_boundary_required != binding.raes_boundary_required,
            "boundary.guest-raes-requirement-mismatch",
        ),
        (
            guest.boot_id != (binding.guest_boot_id or binding.boot_id),
            "boundary.guest-boot-identity-mismatch",
        ),
        (
            guest.guest_daemon_id != binding.guest_daemon_id,
            "boundary.guest-daemon-identity-mismatch",
        ),
        (
            guest.workbench_policy_version != policy.workbench_policy_version,
            "boundary.guest-workbench-policy-mismatch",
        ),
        (
            not guest.observation_complete,
            "boundary.guest-observation-incomplete",
        ),
    )
    findings.extend(code for failed, code in comparisons if failed)
    _append_enforcement_findings(policy, binding, guest, findings)
    _append_probe_findings(policy, binding, guest, findings)
    _append_range_workload_findings(policy, guest, findings)
    allowed = set(policy.docker_authority.allowed_holder_labels)
    unapproved = (
        any(not holder.admitted for holder in guest.docker_authority_holders)
        if policy.seat_component_protection
        else bool(
            {holder.label_selector for holder in guest.docker_authority_holders}
            - allowed
        )
    )
    if unapproved:
        findings.append("boundary.guest-docker-authority-unapproved")
    if any(
        holder.daemon_id != binding.guest_daemon_id
        for holder in guest.docker_authority_holders
    ):
        findings.append("boundary.guest-docker-daemon-mismatch")
    if any(
        holder.privileged
        or holder.host_pid_namespace
        or holder.host_network_namespace
        or holder.device_count
        for holder in guest.docker_authority_holders
    ):
        findings.append("boundary.guest-docker-authority-overprivileged")


def _append_enforcement_findings(
    policy: ApplianceBoundaryPolicy,
    binding: ApplianceBoundaryBinding,
    guest: GuestBoundaryObservation,
    findings: list[str],
) -> None:
    """Require complete, digest-bound readback for every active authority."""

    by_authority = {item.authority: item for item in guest.enforcements}
    if len(by_authority) != len(guest.enforcements):
        findings.append(_INCOMPLETE_ENFORCEMENT)
        return
    platform = by_authority.get("platform")
    if policy.internal_zone_isolation:
        _append_platform_enforcement_findings(platform, binding.policy_digest, findings)
    elif platform is not None:
        findings.append("boundary.guest-unexpected-platform-enforcement")
    seat = by_authority.get("seat-protection")
    if policy.seat_component_protection:
        _append_seat_enforcement_findings(seat, binding.policy_digest, findings)
    elif seat is not None:
        findings.append("boundary.guest-unexpected-seat-protection-enforcement")
    raes = by_authority.get("raes")
    if binding.raes_boundary_required and raes is None:
        findings.append("boundary.guest-raes-enforcement-missing")
    elif raes is not None and raes.source_digest != binding.raes_plan_digest:
        findings.append("boundary.guest-raes-source-mismatch")


def _append_seat_enforcement_findings(
    seat: BoundaryEnforcementObservation | None,
    policy_digest: str,
    findings: list[str],
) -> None:
    """Require complete input protection and an exact range-network scope."""

    if seat is None:
        findings.append(_INCOMPLETE_ENFORCEMENT)
        return
    if seat.source_digest != policy_digest:
        findings.append("boundary.guest-seat-protection-source-mismatch")
    if set(seat.families) != {"bridge", "inet"}:
        findings.append(_INCOMPLETE_ENFORCEMENT)
    coverage = list(seat.network_coverage)
    valid = all(
        value.count("/") == 1
        and value.rsplit("/", 1)[0]
        and value.rsplit("/", 1)[1] in {"ipv4", "ipv6"}
        for value in coverage
    )
    if not coverage or len(coverage) != len(set(coverage)) or not valid:
        findings.append(_INCOMPLETE_ENFORCEMENT)
    if not seat.default_deny_observed:
        findings.append("boundary.guest-default-deny-missing")


def _append_platform_enforcement_findings(
    platform: BoundaryEnforcementObservation | None,
    policy_digest: str,
    findings: list[str],
) -> None:
    """Require complete, digest-bound platform firewall enforcement."""

    if platform is None:
        findings.append(_INCOMPLETE_ENFORCEMENT)
        return
    if platform.source_digest != policy_digest:
        findings.append("boundary.guest-platform-source-mismatch")
    if set(platform.families) != {"bridge", "inet"}:
        findings.append(_INCOMPLETE_ENFORCEMENT)
    if not platform.default_deny_observed:
        findings.append("boundary.guest-default-deny-missing")


def _append_probe_findings(
    policy: ApplianceBoundaryPolicy,
    binding: ApplianceBoundaryBinding,
    guest: GuestBoundaryObservation,
    findings: list[str],
) -> None:
    """Require passing positive and negative probes for each authority."""

    required_authorities = {"platform"} if policy.internal_zone_isolation else set()
    if not policy.internal_zone_isolation and any(
        item.authority == "platform" for item in guest.probes
    ):
        findings.append("boundary.guest-unexpected-platform-probes")
    if binding.raes_boundary_required:
        required_authorities.add("raes")
    for authority in sorted(required_authorities):
        if _probe_failed(guest, authority, "reachable"):
            findings.append(f"boundary.guest-{authority}-positive-probe-failed")
        if _probe_failed(guest, authority, "blocked"):
            findings.append(f"boundary.guest-{authority}-negative-probe-failed")
    if policy.seat_component_protection:
        _append_seat_probe_findings(policy, guest, findings)
    elif any(item.authority == "seat-protection" for item in guest.probes):
        findings.append("boundary.guest-unexpected-seat-protection-probes")


def _append_seat_probe_findings(
    policy: ApplianceBoundaryPolicy,
    guest: GuestBoundaryObservation,
    findings: list[str],
) -> None:
    """Require exact positive and negative coverage for each protected scope."""

    seat_enforcement = next(
        (item for item in guest.enforcements if item.authority == "seat-protection"),
        None,
    )
    coverage = seat_enforcement.network_coverage if seat_enforcement else ()
    expected: dict[str, tuple[str, str | None, int | None]] = {}
    for source in coverage:
        expected[f"seat-protection/{source}/host-reply"] = (
            "reachable",
            None,
            None,
        )
        for component in policy.protected_components:
            expected[f"seat-protection/{source}/{component.probe_identity}"] = (
                "blocked",
                component.protocol,
                component.port,
            )
        for flow in policy.permitted_host_flows:
            for port in flow.ports:
                expected[
                    f"seat-protection/{source}/{flow.probe_identity}/port-{port}"
                ] = ("reachable", flow.protocol, port)
    observed = [item for item in guest.probes if item.authority == "seat-protection"]
    identities = [item.identity for item in observed]
    if set(identities) != set(expected) or len(identities) != len(set(identities)):
        findings.append("boundary.guest-seat-protection-probe-coverage")
        return
    for item in observed:
        expectation, protocol, port = expected[item.identity]
        source = item.identity.removeprefix("seat-protection/").rsplit("/", 1)[0]
        network, family = source.rsplit("/", 1)
        if (
            item.expectation != expectation
            or not item.target_ready
            or not item.passed
            or item.source_network != network
            or item.address_family != family
            or (protocol is not None and item.protocol != protocol)
            or (port is not None and item.port != port)
        ):
            findings.append("boundary.guest-seat-protection-probe-coverage")
            return


def _append_range_workload_findings(
    policy: ApplianceBoundaryPolicy,
    guest: GuestBoundaryObservation,
    findings: list[str],
) -> None:
    """Fail on incomplete authority, namespace, mount, or credential posture."""

    if not policy.seat_component_protection:
        return
    workloads = guest.range_workloads
    identities = [item.identity for item in workloads]
    if (
        not workloads
        or len(identities) != len(set(identities))
        or any(
            not item.receipt_bound or not item.inspect_complete for item in workloads
        )
    ):
        findings.append("boundary.guest-range-observation-incomplete")
    if any(
        item.privileged
        or item.host_pid_namespace
        or item.host_network_namespace
        or item.unapproved_docker_authority
        for item in workloads
    ):
        findings.append("boundary.guest-range-runtime-unapproved")
    if any(item.protected_mount for item in workloads):
        findings.append("boundary.guest-evidence-custody-exposed")
    if any(item.credential_exposure for item in workloads):
        findings.append("boundary.guest-platform-credential-exposed")


def _probe_failed(
    guest: GuestBoundaryObservation, authority: str, expectation: str
) -> bool:
    """Return whether one required authority/expectation has no passing set."""

    scoped = [
        item
        for item in guest.probes
        if item.authority == authority and item.expectation == expectation
    ]
    return not scoped or any(not item.passed for item in scoped)


def _inventory(
    policy: ApplianceBoundaryPolicy,
    binding: ApplianceBoundaryBinding,
    host: HostBoundaryObservation | None,
    guest: GuestBoundaryObservation,
    findings: list[str],
    phase: Literal["image-qualification", "start"],
) -> dict[str, object]:
    """Render bounded machine evidence without raw policy or probe output."""

    return {
        "schema_version": "aptl.appliance-boundary-inventory/v3"
        if policy.seat_component_protection
        else "aptl.appliance-boundary-inventory/v2",
        "phase": phase,
        "policy": {
            "id": policy.policy_id,
            "generation": policy.generation,
            "digest": binding.policy_digest,
            "containment": (
                "internal-zones"
                if policy.internal_zone_isolation
                else (
                    "seat-components" if policy.seat_component_protection else "vm-only"
                )
            ),
        },
        "payload_digest": binding.payload_digest,
        "participant_routes_digest": binding.participant_routes_digest,
        "raes_plan_digest": binding.raes_plan_digest,
        "raes_boundary_required": binding.raes_boundary_required,
        "images": {
            "boundary_helper": binding.boundary_helper_image,
            "egress_proxy": binding.egress_proxy_image,
        },
        "boot_id": binding.boot_id,
        "host_boot_id": binding.host_boot_id or binding.boot_id,
        "guest_boot_id": binding.guest_boot_id or binding.boot_id,
        "host": (
            {"observation_id": host.observation_id, "complete": host.complete}
            if host is not None
            else {"missing": True}
        ),
        "guest": {
            "guest_daemon_id": guest.guest_daemon_id,
            "workbench_policy_version": guest.workbench_policy_version,
            "raes_boundary_required": guest.raes_boundary_required,
            "enforcements": [
                {
                    "authority": item.authority,
                    "source_digest": item.source_digest,
                    "enforcement_digest": item.enforcement_digest,
                    "families": list(item.families),
                    "default_deny_observed": item.default_deny_observed,
                    "network_coverage": list(item.network_coverage),
                }
                for item in guest.enforcements
            ],
            "probes": [
                {
                    "identity": item.identity,
                    "authority": item.authority,
                    "source": item.source,
                    "destination": item.destination,
                    "protocol": item.protocol,
                    "port": item.port,
                    "expectation": item.expectation,
                    "source_network": item.source_network,
                    "address_family": item.address_family,
                    "target_ready": item.target_ready,
                    "passed": item.passed,
                }
                for item in guest.probes
            ],
            "docker_authority_holders": [
                {
                    "identity": item.identity,
                    "label_selector": item.label_selector,
                    "daemon_id": item.daemon_id,
                    "access": item.access,
                    "admitted": item.admitted,
                }
                for item in guest.docker_authority_holders
            ],
            "range_workloads": [
                {
                    "identity": item.identity,
                    "networks": list(item.networks),
                    "receipt_bound": item.receipt_bound,
                    "inspect_complete": item.inspect_complete,
                    "privileged": item.privileged,
                    "host_pid_namespace": item.host_pid_namespace,
                    "host_network_namespace": item.host_network_namespace,
                    "device_count": item.device_count,
                    "unapproved_docker_authority": item.unapproved_docker_authority,
                    "protected_mount": item.protected_mount,
                    "credential_exposure": item.credential_exposure,
                }
                for item in guest.range_workloads
            ],
            "observation_complete": guest.observation_complete,
        },
        "findings": list(findings),
        "passed": not findings,
    }


def _append_host_listener_findings(
    policy: ApplianceBoundaryPolicy, host: HostBoundaryObservation, findings: list[str]
) -> None:
    """Compare mapped listener endpoints with the signed guest publications."""
    expected = {
        (item.audience, item.address, item.port, item.protocol)
        for item in policy.guest_publications
    }
    observed = {
        (
            item.audience,
            item.guest_address or item.address,
            item.guest_port or item.port,
            item.protocol,
        )
        for item in host.listeners
    }
    if observed - expected:
        findings.append("boundary.host-listener-unapproved")
    if expected - observed:
        findings.append("boundary.host-listener-missing")
