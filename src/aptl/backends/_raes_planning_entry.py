"""Inputs and entry point for one adjusted RAES planning operation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from raes_contracts.artifact_requirements import ArtifactAvailabilityContext
from raes_contracts.realization_profiles import PlanProfileAuthority
from raes_contracts.runtime_state import RuntimeSnapshot
from aptl.core.scenario_bundle import ScenarioBundle

if TYPE_CHECKING:
    from raes_processor.models import ExecutionPlan
    from raes_runtime.registry import RuntimeTarget
    from raes_runtime.manager import RuntimeManager as _RaesRuntimeManager


@dataclass(frozen=True)
class AptlPlanningOptions:
    """Optional inputs to one APTL-adjusted RAES planning operation."""

    snapshot: RuntimeSnapshot | None = None
    parameters: Mapping[str, object] | None = None
    profile: str | None = None
    artifact_availability: ArtifactAvailabilityContext | None = None
    profile_authority: PlanProfileAuthority | None = None
    runtime_manager: _RaesRuntimeManager | None = None


def plan_aptl_scenario(
    *,
    target: RuntimeTarget,
    bundle: ScenarioBundle,
    scenario: object,
    options: AptlPlanningOptions | None = None,
) -> ExecutionPlan:
    """Compile and plan through APTL's temporary TechVault compatibility seam."""

    from aptl.backends.raes_planning_compat import AptlRuntimeManager

    selected = options or AptlPlanningOptions()
    manager = selected.runtime_manager or AptlRuntimeManager(target, bundle=bundle)
    plan_options: dict[str, object] = {}
    if selected.parameters is not None:
        plan_options["parameters"] = dict(selected.parameters)
    if selected.profile is not None:
        plan_options["profile"] = selected.profile
    if selected.artifact_availability is not None:
        plan_options["artifact_availability"] = selected.artifact_availability
    if selected.profile_authority is not None:
        plan_options["profile_authority"] = selected.profile_authority
    return (
        manager.plan(scenario, **plan_options)
        if selected.snapshot is None
        else manager.plan(scenario, selected.snapshot, **plan_options)
    )
