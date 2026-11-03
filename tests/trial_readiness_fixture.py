"""The structural fixture's existing sources, selected for readiness tests."""

from dataclasses import replace

from aptl.backends.readiness import ReadinessEnvironment, TrialReadiness
from aptl.core.evidence.adapters.sources import (
    CallableWindowedSource,
    SourceResult,
    WindowedQueryCollector,
)
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.experiment.capture_registry import CollectorRegistry
from aptl.core.trial_readiness import (
    CaptureDestinationReadiness,
    CaptureSourceReadiness,
    ParticipantReadiness,
    ReadinessOwners,
)
from tests.test_experiment_capture_mapping import _covering_registration


def installed_participants(inputs, entry_index=0):
    """Model the participant settings explicitly installed by test composition."""
    return tuple(
        ParticipantReadiness(
            manifest,
            lambda configuration=configuration: configuration.model_copy(deep=True),
            lambda: True,
        )
        for configuration in list(inputs.plan.entries.values())[
            entry_index
        ].participant_configurations
        for manifest in inputs.participant_manifests.values()
        if manifest.identity == configuration.configuration.implementation_identity
    )


def readiness_for(
    inputs, target, store, clock, root, *, owners=None, entry_index=0, **kwargs
):
    registration = _covering_registration(
        capture_offer=target.manifest.observation.capture_offers[0]
    )
    source = CallableWindowedSource(
        lambda start, end: SourceResult(CollectorStatus.EMPTY_OK)
    )
    collector = WindowedQueryCollector(registration.registration_id, source)
    capture = CaptureSourceReadiness(
        collector,
        lambda binding: (
            source.fetch(clock.now(), clock.now()).status is CollectorStatus.EMPTY_OK
        ),
        CaptureDestinationReadiness(lambda required: True),
    )
    selected = ReadinessOwners(
        target_identity=lambda: "approved-daemon",
        containment=lambda: True,
        services=lambda scenario: True,
        captures={registration.registration_id: capture},
        participants=installed_participants(inputs, entry_index),
    )
    if owners:
        selected = replace(selected, **owners)
    return TrialReadiness(
        inputs,
        ReadinessEnvironment(
            target=target,
            artifact_probe=kwargs.pop("artifact_probe", None),
            scenario_root=root / "pack",
            store=store,
            clock=clock,
            owners=selected,
            registry=CollectorRegistry((registration,)),
            **kwargs,
        ),
    )
