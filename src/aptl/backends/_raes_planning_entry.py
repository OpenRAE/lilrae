"""Inputs and entry point for one adjusted RAES planning operation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from raes_contracts.artifact_requirements import ArtifactAvailabilityContext
from raes_contracts.realization_profiles import PlanProfileAuthority
from raes_contracts.planning import PlanScope
from raes_contracts.runtime_state import RuntimeSnapshot
from aptl.core.scenario_bundle import ScenarioBundle

if TYPE_CHECKING:
    from raes_processor.models import ExecutionPlan
    from raes_runtime.registry import RuntimeTarget


@dataclass(frozen=True)
class AptlPlanningOptions:
    """Optional inputs to one APTL-adjusted RAES planning operation."""

    snapshot: RuntimeSnapshot | None = None
    parameters: Mapping[str, object] | None = None
    profile: str | None = None
    artifact_availability: ArtifactAvailabilityContext | None = None
    profile_authority: PlanProfileAuthority | None = None
    run_scope: PlanScope | None = None


def planning_run_scope(
    bundle: ScenarioBundle | None,
    requested: PlanScope | None = None,
    *,
    required: bool = False,
) -> PlanScope:
    """Preserve a sealed trial's run identity when planning its report."""
    selected = requested or PlanScope()
    trial = bundle.trial if isinstance(bundle, ScenarioBundle) else None
    run_id = selected.run_id
    if trial is not None:
        if run_id is not None and run_id != trial.provenance.run_id:
            raise ValueError("family-run-identity-mismatch")
        run_id = trial.provenance.run_id
    return PlanScope(
        target_name=selected.target_name,
        run_id=run_id or (uuid4().hex if required else None),
        instantiation_id=selected.instantiation_id,
    )


def plan_aptl_scenario(
    *,
    target: RuntimeTarget,
    scenario: object,
    options: AptlPlanningOptions | None = None,
) -> ExecutionPlan:
    """Compile and plan through APTL's temporary TechVault compatibility seam."""

    # Planning needs no runtime owner; the one runtime for the run is created
    # for apply (OpenRAE/rae#1660).
    from aptl.backends.raes_planning_compat import plan_for_target

    return plan_for_target(target, scenario, options or AptlPlanningOptions())
