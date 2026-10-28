"""Exact adapter selection and evidence preparation for RAES admission."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from aptl.backends.raes_participant_actions import participant_action_specs_from_runtime_model
from aptl.backends.raes_participant_driver import ParticipantPlanAuthority
from aptl.backends.raes_participant_runtime import AptlParticipantRuntime
from aptl.backends import raes_participant_delivery as participant_delivery

if TYPE_CHECKING:
    from raes_processor.models import ExecutionPlan
    from raes_runtime.registry import RuntimeTarget
    from aptl.backends.raes_realization_model import AptlRealization
    from aptl.backends.raes_participant_delivery import ParticipantDeliveryPlan

from aptl.backends.scenario_family import (
    FamilyTrialInput,
    admit_family_trial,
    require_family_capabilities,
)

from raes import instantiate_scenario, parse_sdl_file

from aptl.backends.identity import (
    APTL_RAES_TARGET_NAME,
    APTL_RAES_TARGET_PROFILE,
    APTL_RAES_TARGET_VERSION,
    BackendIdentity,
)
from aptl.backends.raes_evidence import admit_sdl_evidence
from aptl.backends.scenario_capture import (
    ResolvedScenarioCapture,
    ScenarioCaptureContext,
)
from aptl.backends.scenario_capture_discovery import resolve_scenario_capture
from aptl.backends.scenario_startup import (
    ScenarioStartupSelection,
    select_scenario_startup,
)
from aptl.core.config import AptlConfig
from aptl.core.experiment.capture_plan import CapturePlan, empty_capture_plan
from aptl.core.scenario_bundle import ScenarioBundle


def bind_admission_trial(
    bundle: ScenarioBundle,
    config: AptlConfig,
    trial: FamilyTrialInput | None,
    parameters: Mapping[str, object] | None,
    startup_selection: ScenarioStartupSelection | None,
) -> ScenarioBundle:
    """Validate and pin a sealed trial before selecting executable adapters."""

    if trial is not None:
        if startup_selection is not None or parameters:
            raise ValueError("family-trial-parameter-collision")
        backend_identity = BackendIdentity(
            APTL_RAES_TARGET_NAME,
            APTL_RAES_TARGET_VERSION,
            APTL_RAES_TARGET_PROFILE,
            provider=config.deployment.provider,
            transport=config.deployment.provider,
        )
        admitted_trial = admit_family_trial(bundle, backend_identity, trial)
        selections = require_family_capabilities(admitted_trial)
        installed = (selections[0].distribution, selections[0].distribution_version)
        bundle = cast(
            ScenarioBundle,
            replace(
                bundle,
                trial=replace(
                    admitted_trial,
                    installation=installed,
                    providers=tuple(item.identity() for item in selections),
                ),
            ),
        )
    elif bundle.trial is not None:
        raise ValueError("family-trial-input-required")
    return bundle


def resolve_admission_adapters(
    bundle: ScenarioBundle,
    config: AptlConfig,
    startup_selection: ScenarioStartupSelection | None,
) -> tuple[ScenarioStartupSelection, ResolvedScenarioCapture | None]:
    """Resolve startup and capture adapters once for one exact bundle."""

    startup = startup_selection or select_scenario_startup(bundle)
    identity = bundle.pack_identity
    capture = None
    if identity is not None:
        capture = resolve_scenario_capture(
            ScenarioCaptureContext(
                pack=identity,
                backend=bundle.trial.target.backend
                if bundle.trial
                else BackendIdentity(
                    target_name=APTL_RAES_TARGET_NAME,
                    target_version=APTL_RAES_TARGET_VERSION,
                    profile=APTL_RAES_TARGET_PROFILE,
                    transport=config.deployment.provider,
                ),
                trial=bundle.trial,
            )
        )
    return startup, capture


def prepare_admission_scenario(
    bundle: ScenarioBundle,
    parameters: Mapping[str, object] | None,
    capture_selection: ResolvedScenarioCapture | None,
    *,
    parser: Callable[[Path], object] = parse_sdl_file,
) -> tuple[object, Mapping[str, object] | None, CapturePlan]:
    """Parse, bind, and admit evidence for one scenario exactly once."""

    if bundle.trial is not None:
        if parameters:
            raise ValueError("family-trial-parameter-collision")
        scenario = bundle.trial.scenario
        capture_plan = (
            admit_sdl_evidence(scenario, registry=capture_selection.registry)
            if capture_selection is not None
            else admit_sdl_evidence(scenario)
        )
        return scenario, None, capture_plan
    scenario = parser(bundle.sdl_path)
    if parameters is None:
        from aptl.backends.scenario_runtime_parameters import (
            resolve_runtime_parameters,
        )

        parameters = resolve_runtime_parameters(bundle)
    capture_plan = empty_capture_plan()
    if getattr(scenario, "evidence_requirements", None):
        scenario = instantiate_scenario(scenario, parameters=parameters)
        parameters = None
        if capture_selection is None:
            capture_plan = admit_sdl_evidence(scenario)
        else:
            capture_plan = admit_sdl_evidence(
                scenario,
                registry=capture_selection.registry,
            )
    return scenario, parameters, capture_plan


def bind_admitted_participant_runtime(
    target: RuntimeTarget,
    execution_plan: ExecutionPlan,
    bundle: ScenarioBundle,
    config: AptlConfig,
    realization: AptlRealization | None,
    scenario: object,
    capture_plan: CapturePlan,
) -> ParticipantDeliveryPlan:
    """Bind participant authority and capture to the single admitted plan."""

    participant_action_specs = participant_action_specs_from_runtime_model(
        execution_plan.model,
        provisioning_plan=execution_plan.provisioning,
        bundle=bundle,
        config=config,
        realization=realization,
    )
    participant_runtime = target.participant_runtime
    if isinstance(participant_runtime, AptlParticipantRuntime):
        participant_runtime.action_specs.update(participant_action_specs)
        participant_runtime.plan_authority = ParticipantPlanAuthority(
            execution_plan,
            bundle.sdl_path,
        )
    participant_delivery_plan = participant_delivery.bind_participant_delivery_capture(
        participant_delivery.build_participant_delivery_plan(
            scenario,
            execution_plan.model,
        ),
        capture_plan,
    )
    return participant_delivery_plan

__all__ = ["prepare_admission_scenario", "resolve_admission_adapters"]
