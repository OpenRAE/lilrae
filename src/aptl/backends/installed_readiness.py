"""Compose trial readiness from the installed lab's existing concrete owners."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from raes_processor.trial_realization import TrialRealizationInputs
from raes_runtime.registry import RuntimeTarget

from aptl.backends.readiness import ReadinessEnvironment, TrialReadiness
from aptl.core.correlation.clock import ClockProvider
from aptl.core.evidence.adapters.sources import WindowedQueryCollector
from aptl.core.execution_boundary import (
    BoundaryProbeBackend,
    BoundarySelection,
    capture_execution_boundary,
)
from aptl.core.experiment.capture_registry import CollectorRegistry
from aptl.core.placement_readiness import AppliancePlacementReadiness
from aptl.core.runstore import LocalRunStore
from aptl.core.sysreqs import check_scenario_max_map_count, docker_mode_for_containment
from aptl.core.trial_readiness import (
    CaptureDestinationReadiness,
    CaptureSourceReadiness,
    ParticipantReadiness,
    ReadinessOwners,
)
from aptl.utils.pathsafe import (
    create_exclusive_nofollow,
    open_private_dir_contained_nofollow,
    remove_contained_nofollow,
)
from aptl.utils.probe_execution import ProbeProcessRunner


class ReadinessBackend(BoundaryProbeBackend, Protocol):
    """The selected deployment owner's existing read-only placement surface."""

    def daemon_identity(self) -> str: ...


@dataclass(frozen=True)
class InstalledReadiness:
    """An existing approved placement, not authority to approve a new target.

    ``approved_boundary`` is the selected lab owner's bound placement record.
    Readiness checks fresh endpoint and daemon facts against that exact record.
    Unverified VM labels do not become a new containment qualification.
    Participant ports come from the installed executor's ``readiness_owner``.
    Collectors are the same instances supplied to ordinary capture acquisition.
    """

    backend: ReadinessBackend
    approved_boundary: BoundarySelection
    participants: tuple[ParticipantReadiness, ...]
    collectors: Mapping[str, WindowedQueryCollector]
    store: LocalRunStore
    clock: ClockProvider
    process_runner: ProbeProcessRunner
    containment: AppliancePlacementReadiness | None = None
    source_clocks: Mapping[str, ClockProvider] = field(default_factory=dict)

    def containment_ready(self) -> bool:
        """Reobserve the approved lab owner without changing its containment claim."""
        if self.containment is None:
            return False
        current = capture_execution_boundary(self.backend)
        selected = self.approved_boundary
        observed = {"observed", "partial"}
        statuses_ready = (
            current.observation.observation_status in observed
            and selected.observation.observation_status in observed
        )
        return (
            bool(selected.endpoint_digest and selected.daemon_digest)
            and statuses_ready
            and (
                current.endpoint_digest,
                current.daemon_digest,
                current.observation.transport,
                current.observation.host_containment,
                current.observation.profile_ref,
            )
            == (
                selected.endpoint_digest,
                selected.daemon_digest,
                selected.observation.transport,
                selected.observation.host_containment,
                selected.observation.profile_ref,
            )
            and self.containment.check(self.backend.daemon_identity())
        )

    def destination_ready(self, required_bytes: int) -> bool:
        """Prove the effective local writer and space with existing safe operations."""
        fd = open_private_dir_contained_nofollow(
            self.store.base_dir, Path(".readiness")
        )
        try:
            info = os.fstatvfs(fd)
            if info.f_bavail * info.f_frsize < required_bytes:
                return False
        finally:
            os.close(fd)
        relative = Path(".readiness") / uuid4().hex
        try:
            create_exclusive_nofollow(self.store.base_dir, relative, b"readiness\n")
        finally:
            removed = remove_contained_nofollow(self.store.base_dir, relative)
        return removed

    def resources_ready(self, _scenario: object, minimum: int) -> bool:
        """Use the scenario's exact demand and selected daemon's system owner."""
        if not self.containment_ready():
            return False
        mode = docker_mode_for_containment(
            self.approved_boundary.observation.host_containment
        )
        result = check_scenario_max_map_count(minimum, selected_mode=mode)
        return result.applicable is True and result.passed is True

    def owners(self) -> ReadinessOwners:
        """Wire source probes and the effective destination without no-op checks."""
        destination = CaptureDestinationReadiness(self.destination_ready)
        captures = {
            key: CaptureSourceReadiness(
                collector=collector,
                check=lambda _binding, collector=collector: collector.check_readiness(
                    self.clock
                ),
                destination=destination,
                clock=self.source_clocks.get(key),
            )
            for key, collector in self.collectors.items()
            if key == collector.registration_id
        }
        return ReadinessOwners(
            target_identity=self.backend.daemon_identity,
            containment=self.containment_ready,
            participants=self.participants,
            captures=captures,
            resources=self.resources_ready,
        )

    def create_gate(
        self,
        inputs: TrialRealizationInputs,
        target: RuntimeTarget,
        scenario_root: Path,
        registry: CollectorRegistry,
    ) -> TrialReadiness:
        """Attach the fixed native gate before the public runtime admits trials."""
        if getattr(target.provisioner, "deployment_backend", None) is not self.backend:
            raise ValueError("trial-readiness-backend-mismatch")
        return TrialReadiness(
            inputs,
            ReadinessEnvironment(
                target=target,
                artifact_probe=self.backend,
                scenario_root=scenario_root,
                store=self.store,
                clock=self.clock,
                owners=self.owners(),
                registry=registry,
                process_runner=self.process_runner,
            ),
        )
