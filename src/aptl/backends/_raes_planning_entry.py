"""Inputs and entry point for one adjusted RAES planning operation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from raes_contracts.artifact_requirements import ArtifactAvailabilityContext
from raes_contracts.realization_profiles import PlanProfileAuthority
from raes_contracts.planning import PlanScope
from raes_contracts.runtime_state import RuntimeSnapshot

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
