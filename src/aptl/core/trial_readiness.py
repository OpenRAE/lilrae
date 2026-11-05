"""Fixed native owner inputs for required trial readiness; no check registry."""

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol, runtime_checkable

from raes.scenario import InstantiatedScenario
from raes_contracts.canonical import canonical_contract_digest
from raes_contracts.contracts import (
    ArtifactAvailabilityContext,
    ParticipantConfigurationResultModel,
    ParticipantImplementationManifestModel,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import ApplyResult
from raes_processor.trial_realization import TrialRealizationInputs

from aptl.core.correlation.clock import ClockProvider
from aptl.core.evidence.protocol import Collector
from aptl.core.experiment.capture_plan import CapturePlan
from aptl.core.experiment.capture_registry import CaptureBinding
from aptl.core.readiness_observer import ReadinessObserver


class TrialReadinessGate(Protocol):
    """Authority shared by the trial wrapper and its installed effect adapters."""

    def require_provisioning(self) -> None: ...

    def require_live(self) -> None: ...

    def after_provisioning(
        self, plan: ProvisioningPlan, result: ApplyResult
    ) -> ApplyResult: ...


@runtime_checkable
class ProvisionerReadinessPort(Protocol):
    """An installed provisioner which gates its completed native realization."""

    readiness: TrialReadinessGate | None
    readiness_requires_runner: bool

    def readiness_artifacts(
        self, scenario: InstantiatedScenario, probe: object | None, root: Path
    ) -> ArtifactAvailabilityContext: ...
    def readiness_contract(self, plan: ProvisioningPlan, root: Path) -> bool: ...
    def readiness_services(self, plan: ProvisioningPlan) -> bool: ...
    def readiness_resource_minimum(
        self, inputs: TrialRealizationInputs, entry: str
    ) -> int | None: ...


@runtime_checkable
class EffectReadinessPort(Protocol):
    """An installed effect adapter controlled through its existing readiness gate."""

    readiness: TrialReadinessGate | None


@dataclass(frozen=True)
class ParticipantReadiness:
    """The installed implementation's complete settings and access operation.

    The operation verifies the selected implementation/build and approved
    provider access. The configuration reader returns actual installed settings,
    including complete request controls, rather than a model label.
    """

    manifest: ParticipantImplementationManifestModel = field(repr=False)
    configuration: Callable[[], ParticipantConfigurationResultModel] = field(repr=False)
    check: Callable[[], bool] = field(repr=False)


@dataclass(frozen=True)
class CaptureDestinationReadiness:
    """One effective writer's capacity check, shared by co-located outputs.

    The operation uses the destination owner's approved transport and enforces
    time/output limits. It must check write access and any effective quota.
    Reuse this same object for captures sharing a filesystem or writer quota.
    """

    check: Callable[[int], bool] = field(repr=False)


@dataclass(frozen=True)
class CaptureSourceReadiness:
    """An installed collector, its read-only source check, and output owner.

    Clock tolerance comes from the selected, pinned collector declaration.
    Omitting this source's clock cannot remove a declared accuracy requirement.
    No source content or credentials are returned by these operations.
    """

    collector: Collector = field(repr=False)
    check: Callable[[CaptureBinding], bool] = field(repr=False)
    destination: CaptureDestinationReadiness
    clock: ClockProvider | None = field(default=None, repr=False)

    def clock_is_ready(self, binding: CaptureBinding, maximum_ms: int) -> bool:
        """Require this source's synchronized clock within its pinned tolerance."""
        if type(maximum_ms) is not int or maximum_ms < 0 or self.clock is None:
            return False
        context = self.clock.clock_context(
            source_kind="collector", source_id=binding.registration_id
        )
        try:
            offset = _clock_milliseconds(context.measured_offset)
            uncertainty = _clock_milliseconds(context.uncertainty)
            error = abs(offset) + uncertainty
        except InvalidOperation, TypeError, ValueError:
            return False
        return (
            context.source_id == binding.registration_id
            and context.source_kind == "collector"
            and context.synchronization_status == "synchronized"
            and uncertainty >= 0
            and error.is_finite()
            and error <= maximum_ms
        )


@dataclass(frozen=True)
class ReadinessOwners:
    """Existing approved native owners selected by trusted composition.

    These are fixed capabilities, not plugins or experiment-selected callbacks.
    Each operation is read-only and must bound bytes at its transport boundary.
    The gate also bounds its call and accepts only a strict positive result.
    Missing required operations fail closed. No ambient owner is discovered.
    """

    target_identity: Callable[[], str] | None = field(default=None, repr=False)
    containment: Callable[[], bool] | None = field(default=None, repr=False)
    participants: tuple[ParticipantReadiness, ...] = ()
    services: Callable[[InstantiatedScenario], bool] | None = field(
        default=None, repr=False
    )
    captures: Mapping[str, CaptureSourceReadiness] = field(default_factory=dict)
    resources: Callable[[InstantiatedScenario, int], bool] | None = field(
        default=None, repr=False
    )


def _clock_milliseconds(value: str | None) -> Decimal:
    """Parse a bounded explicit duration without locale or floating point loss."""
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d+)?|\.\d+))(ns|us|ms|s)", value, re.ASCII)
    if match is None:
        raise ValueError
    scale = {
        "ns": Decimal("0.000001"),
        "us": Decimal("0.001"),
        "ms": Decimal(1),
        "s": Decimal(1000),
    }
    return Decimal(match[1]) * scale[match[2]]


def observe_capture_readiness(
    plan: CapturePlan,
    captures: Mapping[str, CaptureSourceReadiness],
    observer: ReadinessObserver,
    checks: list[Diagnostic],
) -> None:
    """Check each pinned capture obligation against its installed source owner."""
    destinations = {}
    for index, admitted in enumerate(plan.bindings):
        binding = admitted.runtime_binding(plan.plan_id)
        source = captures.get(binding.registration_id)
        name = f"capture-{index}"
        if source is None:
            observer.check(checks, name + "-source", None)
            continue
        observer.check(
            checks,
            name + "-collector",
            lambda source=source, binding=binding: (
                isinstance(source.collector, Collector)
                and source.collector.registration_id == binding.registration_id
            ),
        )
        observer.check(
            checks,
            name + "-source",
            lambda source=source, binding=binding: source.check(binding),
        )
        if admitted.clock_accuracy_ms is not None:
            observer.check(
                checks,
                name + "-clock",
                lambda source=source, binding=binding, admitted=admitted: (
                    source.clock_is_ready(binding, admitted.clock_accuracy_ms)
                ),
            )
        key = id(source.destination)
        check, required = destinations.get(key, (source.destination.check, 0))
        destinations[key] = (check, required + binding.limits.max_bytes)
    for index, (check, required) in enumerate(destinations.values()):
        observer.check(
            checks,
            f"capture-storage-{index}",
            lambda check=check, required=required: check(required),
        )


def _installed_participants(
    owners: tuple[ParticipantReadiness, ...],
    observer: ReadinessObserver,
) -> dict[str, tuple[ParticipantReadiness, ParticipantConfigurationResultModel]] | None:
    """Validate complete installed configurations before matching requests."""
    installed = {}
    for owner in owners:
        current = observer.call(owner.configuration)
        if not isinstance(current, ParticipantConfigurationResultModel):
            return None
        current = ParticipantConfigurationResultModel.model_validate(
            current.model_dump(mode="json")
        )
        if (
            current.participant_address in installed
            or canonical_contract_digest(current.configuration)
            != current.configuration_digest
        ):
            return None
        installed[current.participant_address] = (owner, current)
    return installed


def _participant_is_ready(
    configuration: ParticipantConfigurationResultModel,
    selected: tuple[ParticipantReadiness, ParticipantConfigurationResultModel] | None,
    observer: ReadinessObserver,
) -> bool:
    """Match exact sealed settings and observe their installed owner."""
    if selected is None:
        return False
    owner, current = selected
    return (
        current.model_dump(mode="json") == configuration.model_dump(mode="json")
        and canonical_contract_digest(owner.manifest) == configuration.manifest_digest
        and observer.call(owner.check) is True
    )


def observe_participant_readiness(
    configurations: Sequence[ParticipantConfigurationResultModel],
    owners: tuple[ParticipantReadiness, ...],
    observer: ReadinessObserver,
) -> bool:
    """Require each sealed participant configuration to match its actual owner."""
    installed = _installed_participants(owners, observer)
    return installed is not None and all(
        _participant_is_ready(
            configuration, installed.get(configuration.participant_address), observer
        )
        for configuration in configurations
    )
