"""Public RAES reconstruction and ordinary installed-backend qualification."""

from dataclasses import dataclass
from pathlib import Path

from raes_contracts.errors import InvalidInputError
from raes_contracts.trial_unit import TrialUnitRequest
from raes_processor.planner import realization_authority_diagnostics
from raes_processor.trial_realization import (
    TrialRealization,
    TrialRealizationInputs,
    instantiate_admitted_trial_entry,
    realize_admitted_trial_entry,
)
from raes_runtime.registry import RuntimeTarget

from aptl.core.trial_readiness import ProvisionerReadinessPort


@dataclass
class ReadinessApparatus:
    """Reconstruct exact admitted plans and ask their native owner for readback."""

    inputs: TrialRealizationInputs
    target: RuntimeTarget
    artifact_probe: object | None
    scenario_root: Path

    def derive(self, request: TrialUnitRequest) -> TrialRealization | None:
        """Reconstruct the selected public entry without native effects."""
        provisioner = self.target.provisioner
        if request.plan.model_dump(mode="json") != self.inputs.plan.model_dump(
            mode="json"
        ) or not isinstance(provisioner, ProvisionerReadinessPort):
            return None
        scenario = instantiate_admitted_trial_entry(
            plan=request.plan,
            plan_entry_id=request.plan_entry_id,
            family=self.inputs.family,
        )
        availability = provisioner.readiness_artifacts(
            scenario, self.artifact_probe, self.scenario_root
        )
        try:
            realized = realize_admitted_trial_entry(
                inputs=self.inputs,
                plan_entry_id=request.plan_entry_id,
                artifact_availability=availability,
                target_name=self.target.name,
            )
        except InvalidInputError:
            return None
        return (
            realized
            if self._matches(request, realized) and self._runtime_ready(realized)
            else None
        )

    def _matches(self, request: TrialUnitRequest, realized: TrialRealization) -> bool:
        """Require all supplied plan and snapshot identities to agree."""
        return (
            realized.snapshot_digest == request.instantiated_sdl_digest
            and realized.execution_plan.manifest == self.target.manifest
            and realized.provisioning_plan == request.provisioning_plan
            and realized.orchestration_plan == request.orchestration_plan
            and realized.evaluation_plan == request.evaluation_plan
        )

    def _runtime_ready(self, realized: TrialRealization) -> bool:
        """Require installed participant planning checks when a runtime exists."""
        runtime = self.target.participant_runtime
        if runtime is None:
            return True
        diagnostics = getattr(runtime, "readiness_planning_diagnostics", None)
        return callable(diagnostics) and not diagnostics(realized.execution_plan.model)

    def native_contract(self, realized: TrialRealization) -> bool:
        """Require public authority and ordinary native qualification."""
        plan = realized.execution_plan.provisioning
        return (
            not realization_authority_diagnostics(plan, self.target.manifest)
            and self.target.provisioner.readiness_contract(plan, self.scenario_root)
            is True
        )

    def native_services(self, realized: TrialRealization) -> bool:
        """Read the selected native provisioner's required service state."""
        return (
            self.target.provisioner.readiness_services(
                realized.execution_plan.provisioning
            )
            is True
        )

    def required_resource_minimum(self, plan_entry_id: str) -> int | None:
        """Ask the installed startup owner for the selected entry's exact demand."""
        return self.target.provisioner.readiness_resource_minimum(
            self.inputs, plan_entry_id
        )
