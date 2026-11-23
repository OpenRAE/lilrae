"""Positive containment evidence from the approved placement's ordinary owner."""

from collections.abc import Callable
from dataclasses import dataclass

from aptl.core.appliance_boundary import (
    ApplianceBoundaryBinding,
    ApplianceBoundaryPolicy,
)
from aptl.core.appliance_boundary_inventory import qualify_appliance_boundary
from aptl.core.appliance_boundary_observation import (
    GuestBoundaryObservation,
    HostBoundaryObservation,
)


@dataclass(frozen=True)
class AppliancePlacementReadiness:
    """Fresh host and guest observations for an existing approved placement.

    Observation methods belong to the installed placement owner. The gate does
    not discover a hypervisor, launch a VM, or confer approval on this policy.
    The ordinary qualifier requires perimeter, enforcement and identity proof.
    """

    policy: ApplianceBoundaryPolicy
    binding: ApplianceBoundaryBinding
    host: Callable[[], HostBoundaryObservation | None]
    guest: Callable[[], GuestBoundaryObservation]

    def check(self, daemon_id: str) -> bool:
        """Refuse absent, incomplete, stale or mismatched positive evidence."""
        if self.binding.guest_daemon_id != daemon_id:
            return False
        host, guest = self.host(), self.guest()
        if host is not None:
            host = HostBoundaryObservation.model_validate_json(host.model_dump_json())
        guest = GuestBoundaryObservation.model_validate_json(guest.model_dump_json())
        return (
            qualify_appliance_boundary(self.policy, self.binding, host, guest).passed
            is True
        )
