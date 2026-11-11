"""Bounded rendering for appliance-boundary qualification evidence."""

from __future__ import annotations

from typing import Literal

from aptl.core.appliance_boundary import (
    ApplianceBoundaryBinding,
    ApplianceBoundaryPolicy,
)
from aptl.core.appliance_boundary_observation import (
    GuestBoundaryObservation,
    HostBoundaryObservation,
)


def render_boundary_inventory(
    policy: ApplianceBoundaryPolicy,
    binding: ApplianceBoundaryBinding,
    host: HostBoundaryObservation | None,
    guest: GuestBoundaryObservation,
    findings: list[str],
    phase: Literal["image-qualification", "start"],
) -> dict[str, object]:
    """Render bounded machine evidence without raw policy or probe output."""

    containment = "vm-only"
    if policy.internal_zone_isolation:
        containment = "internal-zones"
    elif policy.seat_component_protection:
        containment = "seat-components"
    return {
        "schema_version": "aptl.appliance-boundary-inventory/v3"
        if policy.seat_component_protection
        else "aptl.appliance-boundary-inventory/v2",
        "phase": phase,
        "policy": {
            "id": policy.policy_id,
            "generation": policy.generation,
            "digest": binding.policy_digest,
            "containment": containment,
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
