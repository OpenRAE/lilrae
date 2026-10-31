"""Canonical full-TechVault platform boundary policy for appliance delivery."""

from __future__ import annotations

import os
from pathlib import Path

import rfc8785

from aptl.core.appliance_boundary import ApplianceBoundaryPolicy


def full_techvault_boundary_policy() -> ApplianceBoundaryPolicy:
    """Return the signed protected-seat contract without scenario topology."""

    return ApplianceBoundaryPolicy.model_validate(
        {
            "schema_version": "aptl.appliance-boundary/v3",
            "policy_id": "techvault-full",
            "generation": 4,
            "workbench_policy_version": "participant-workbench-profile/v1",
            "default_deny": True,
            "guest_publications": [
                {
                    "audience": "participant",
                    "address": "127.0.0.1",
                    "port": 8080,
                    "protocol": "tcp",
                },
            ],
            "docker_authority": {
                "allowed_holder_labels": [],
                "require_guest_daemon": True,
            },
            "protected_components": [
                {
                    "component_class": "management-control",
                    "probe_identity": "seat-management-control",
                    "protocol": "tcp",
                    "port": 43101,
                    "purpose": "seat management and control boundary",
                },
                {
                    "component_class": "evidence-capture",
                    "probe_identity": "seat-evidence-capture",
                    "protocol": "tcp",
                    "port": 43102,
                    "purpose": "evidence capture authority boundary",
                },
                {
                    "component_class": "evidence-store",
                    "probe_identity": "seat-evidence-store",
                    "protocol": "tcp",
                    "port": 43103,
                    "purpose": "evidence storage boundary",
                },
                {
                    "component_class": "docker-authority",
                    "probe_identity": "seat-docker-authority",
                    "protocol": "tcp",
                    "port": 43104,
                    "purpose": "guest Docker authority boundary",
                },
                {
                    "component_class": "credentials",
                    "probe_identity": "seat-credentials",
                    "protocol": "tcp",
                    "port": 43105,
                    "purpose": "platform credential boundary",
                },
            ],
            "permitted_host_flows": [],
        }
    )


def write_full_techvault_boundary_policy(output: Path) -> ApplianceBoundaryPolicy:
    """Create the canonical policy once using deterministic bytes."""

    policy = full_techvault_boundary_policy()
    output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    descriptor = os.open(
        output,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
        0o444,
    )
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(rfc8785.dumps(policy.model_dump(mode="json")))
        handle.flush()
        os.fsync(handle.fileno())
    return policy
