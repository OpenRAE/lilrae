"""Scoped ownership transfer between the manager and a RAES control plane."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from raes_contracts.runtime_state import RuntimeSnapshot
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.runtime_resource_ownership import RuntimeResourceClaim


class LilraeRuntimeHandoffMixin:
    """Extend the pinned RAES manager with a sequential control-plane phase.

    Keep the initialized clock and scheduler on their original manager. RAES 7
    has no public manager handoff method; reacquisition uses its own claim
    constructor, including its exclusion of active or unresolved owners.
    """

    @contextmanager
    def control_plane(
        self,
        *,
        snapshot_transform: Callable[[RuntimeSnapshot], RuntimeSnapshot] | None = None,
        **options: object,
    ) -> Iterator[RuntimeControlPlane]:
        """Drain the manager, run one control plane, then resume its snapshot.

        A failed drain never opens a second owner. Construction, operation, or
        close exceptions leave the manager closed, so startup must fail rather
        than resume from an uncertain state. Only a normally closed control
        plane hands its authoritative snapshot back to the manager.
        """

        with self._control_plane_handoff_lock:
            if self._resource_claim.closed:
                raise RuntimeError("runtime manager is closed")
            self.close()
            snapshot = self.snapshot
            if snapshot_transform is not None:
                snapshot = snapshot_transform(snapshot)
            options.setdefault(
                "information_state_context_resolver",
                self._information_state_context_resolver,
            )
            with RuntimeControlPlane(
                self._target, initial_snapshot=snapshot, **options
            ) as control_plane:
                yield control_plane
                snapshot = control_plane.snapshot

            # Do not clear or reuse a closed claim. The canonical constructor
            # refuses reacquisition if shutdown retained an unresolved owner.
            self._snapshot = snapshot
            self._resource_claim = RuntimeResourceClaim(self, self._target)
            if not self._start_participant_clock_driver():
                self.close()
                raise RuntimeError("runtime manager clock driver could not resume")
