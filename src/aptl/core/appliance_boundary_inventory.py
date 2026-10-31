"""Fresh fatal appliance-boundary inventory and verdict."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from aptl.core.appliance_boundary import (
    ApplianceBoundaryBinding,
    ApplianceBoundaryPolicy,
)
from aptl.core.appliance_boundary_observation import (
    BoundaryEndpoint,
    BoundaryEnforcementObservation,
    BoundaryProbeObservation,
    DockerAuthorityHolder,
    GuestBoundaryObservation,
    HostBoundaryObservation,
    RangeWorkloadObservation,
)
from aptl.core._appliance_boundary_inventory_render import (
    render_boundary_inventory,
)
from aptl.utils.redaction import redact

_INCOMPLETE_ENFORCEMENT = "boundary.guest-enforcement-incomplete"


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
    inventory = render_boundary_inventory(policy, binding, host, guest, findings, phase)
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
    expected = _seat_probe_expectations(policy, coverage)
    observed = [item for item in guest.probes if item.authority == "seat-protection"]
    identities = [item.identity for item in observed]
    coverage_complete = set(identities) == set(expected) and len(identities) == len(
        set(identities)
    )
    if not coverage_complete or any(
        not _seat_probe_matches(item, expected[item.identity]) for item in observed
    ):
        findings.append("boundary.guest-seat-protection-probe-coverage")


def _seat_probe_expectations(
    policy: ApplianceBoundaryPolicy,
    coverage: tuple[str, ...],
) -> dict[str, tuple[str, str | None, int | None]]:
    """Build the exact signed positive and negative seat probe matrix."""

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
    return expected


def _seat_probe_matches(
    item: BoundaryProbeObservation,
    expected: tuple[str, str | None, int | None],
) -> bool:
    """Return whether one fresh probe exactly satisfies its matrix entry."""

    expectation, protocol, port = expected
    source = item.identity.removeprefix("seat-protection/").rsplit("/", 1)[0]
    network, family = source.rsplit("/", 1)
    return (
        item.expectation == expectation
        and item.target_ready
        and item.passed
        and item.source_network == network
        and item.address_family == family
        and (protocol is None or item.protocol == protocol)
        and (port is None or item.port == port)
    )


def _append_range_workload_findings(
    policy: ApplianceBoundaryPolicy,
    guest: GuestBoundaryObservation,
    findings: list[str],
) -> None:
    """Fail on incomplete authority, namespace, mount, or credential posture."""

    if not policy.seat_component_protection:
        return
    workloads = guest.range_workloads
    if _range_observation_incomplete(workloads):
        findings.append("boundary.guest-range-observation-incomplete")
    if any(_range_runtime_unapproved(item) for item in workloads):
        findings.append("boundary.guest-range-runtime-unapproved")
    if any(item.protected_mount for item in workloads):
        findings.append("boundary.guest-evidence-custody-exposed")
    if any(item.credential_exposure for item in workloads):
        findings.append("boundary.guest-platform-credential-exposed")


def _range_observation_incomplete(
    workloads: tuple[RangeWorkloadObservation, ...],
) -> bool:
    """Return whether workload identity or inspection coverage is incomplete."""

    identities = [item.identity for item in workloads]
    return (
        not workloads
        or len(identities) != len(set(identities))
        or any(
            not item.receipt_bound or not item.inspect_complete for item in workloads
        )
    )


def _range_runtime_unapproved(item: RangeWorkloadObservation) -> bool:
    """Return whether one ordinary workload holds a forbidden runtime capability."""

    return (
        item.privileged
        or item.host_pid_namespace
        or item.host_network_namespace
        or item.unapproved_docker_authority
    )


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
