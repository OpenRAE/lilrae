"""A neutral protected-seat boundary policy for generic appliance tests (#1700).

It declares the five protected seat components and no scenario topology, so
generic appliance, boundary, and seat-image tests need no scenario-named
policy. Import-safe; named without a ``test_`` prefix so pytest does not
collect it.
"""

from __future__ import annotations

from aptl.core.appliance_boundary import ApplianceBoundaryPolicy

_COMPONENTS = (
    ("management-control", 43101, "seat management and control boundary"),
    ("evidence-capture", 43102, "evidence capture authority boundary"),
    ("evidence-store", 43103, "evidence storage boundary"),
    ("docker-authority", 43104, "guest Docker authority boundary"),
    ("credentials", 43105, "platform credential boundary"),
)


def protected_seat_policy() -> ApplianceBoundaryPolicy:
    """Return a default-deny policy that protects every seat component."""

    return ApplianceBoundaryPolicy.model_validate(
        {
            "schema_version": "aptl.appliance-boundary/v3",
            "policy_id": "protected-seat-fixture",
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
                    "component_class": component,
                    "probe_identity": f"seat-{component}",
                    "protocol": "tcp",
                    "port": port,
                    "purpose": purpose,
                }
                for component, port, purpose in _COMPONENTS
            ],
            "permitted_host_flows": [],
        }
    )


__all__ = ["protected_seat_policy"]
