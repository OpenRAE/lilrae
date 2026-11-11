"""Native provisioner readback behind the core readiness owner interface."""

from dataclasses import replace
from pathlib import Path
from typing import cast

from raes.scenario import InstantiatedScenario
from raes_contracts.contracts import ArtifactAvailabilityContext
from raes_contracts.planning import ChangeAction, ProvisioningPlan
from raes_processor.trial_realization import TrialRealizationInputs

from aptl.backends.raes_artifact_availability import (
    ArtifactProbe,
    artifact_availability_for_scenario,
)
from aptl.core.lab_types import StartupOutcome
from aptl.core.scenario_bundle import ScenarioBundle


class NativeReadinessMixin:
    """Read-only operations of the installed native provisioner."""

    readiness_requires_runner: bool = True

    @staticmethod
    def _cleanup_only(plan: object) -> bool:
        """Allow only nonempty deletion plans through the cleanup policy path."""
        return (
            isinstance(plan, ProvisioningPlan)
            and bool(plan.operations)
            and all(
                operation.action is ChangeAction.DELETE for operation in plan.operations
            )
        )

    @staticmethod
    def readiness_artifacts(
        scenario: InstantiatedScenario, probe: object | None, root: Path
    ) -> ArtifactAvailabilityContext:
        """Read artifact availability without fetching or materializing content."""
        if probe is None:
            return ArtifactAvailabilityContext()
        return artifact_availability_for_scenario(
            scenario,
            cast(ArtifactProbe, probe),
            allow_remote=False,
            scenario_root=root,
            materialize=False,
        )

    def readiness_contract(self, plan: ProvisioningPlan, root: Path) -> bool:
        """Qualify the exact deployment through the existing native owner."""
        if any(item.is_error for item in self.validate(plan)):
            return False
        realization = self.realize_plan(plan)
        spec = realization.deployment_spec(
            self.selected_profiles(realization),
            startup_selection=self.startup_selection,
        )
        result = self.deployment_backend.qualify_runtime_materialization(
            spec, scenario_root=root
        )
        return result.success is True and result.outcome is StartupOutcome.READY

    def readiness_services(self, plan: ProvisioningPlan) -> bool:
        """Read back only the services required by this admitted plan."""
        realization = self.realize_plan(plan)
        spec = realization.deployment_spec(
            self.selected_profiles(realization),
            startup_selection=self.startup_selection,
        )
        return self.deployment_backend.verify_required_service_readiness(spec)

    def readiness_resource_minimum(
        self, inputs: TrialRealizationInputs, plan_entry_id: str
    ) -> int | None:
        """Re-resolve the exact entry's startup demand and reject stale selection."""
        from aptl.backends._raes_admission_helpers import bind_admission_trial
        from aptl.backends.scenario_family import FamilyTrialInput
        from aptl.backends.scenario_startup import select_scenario_startup

        bundle = self.bundle
        selected = self.startup_selection
        if bundle.pack_identity is None:
            # The supported project-tree baseline has no family adapter.
            if selected is not None and (
                selected.plan is not None
                or selected.provider is not None
                or selected.identity is not None
                or selected.trial is not None
            ):
                raise ValueError("trial-resource-selection-mismatch")
            return None
        bound = bind_admission_trial(
            cast(ScenarioBundle, replace(bundle, trial=None)),
            self.config,
            FamilyTrialInput(inputs.plan, plan_entry_id, inputs.family),
            None,
            None,
        )
        required = select_scenario_startup(bound)
        if selected is None or selected != required:
            raise ValueError("trial-resource-selection-mismatch")
        if required.plan is None:
            raise ValueError("trial-resource-selection-unavailable")
        return required.plan.minimum_max_map_count
