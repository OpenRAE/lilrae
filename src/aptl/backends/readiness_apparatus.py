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
    inputs: TrialRealizationInputs
    target: RuntimeTarget
    artifact_probe: object | None
    scenario_root: Path

    def derive(self, request: TrialUnitRequest) -> TrialRealization | None:
        if request.plan.model_dump(mode="json") != self.inputs.plan.model_dump(
            mode="json"
        ):
            return None
        scenario = instantiate_admitted_trial_entry(
            plan=request.plan,
            plan_entry_id=request.plan_entry_id,
            family=self.inputs.family,
        )
        provisioner = self.target.provisioner
        if not isinstance(provisioner, ProvisionerReadinessPort):
            return None
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
        if (
            realized.snapshot_digest != request.instantiated_sdl_digest
            or realized.execution_plan.manifest != self.target.manifest
            or realized.provisioning_plan != request.provisioning_plan
            or realized.orchestration_plan != request.orchestration_plan
            or realized.evaluation_plan != request.evaluation_plan
        ):
            return None
        runtime = self.target.participant_runtime
        if runtime is not None:
            diagnostics = getattr(runtime, "readiness_planning_diagnostics", None)
            if not callable(diagnostics) or diagnostics(realized.execution_plan.model):
                return None
        return realized

    def native_contract(self, realized: TrialRealization) -> bool:
        plan = realized.execution_plan.provisioning
        return (
            not realization_authority_diagnostics(plan, self.target.manifest)
            and self.target.provisioner.readiness_contract(plan, self.scenario_root)
            is True
        )

    def native_services(self, realized: TrialRealization) -> bool:
        return (
            self.target.provisioner.readiness_services(
                realized.execution_plan.provisioning
            )
            is True
        )

    def required_resource_minimum(self, plan_entry_id: str) -> int | None:
        return self.target.provisioner.readiness_resource_minimum(
            self.inputs, plan_entry_id
        )
