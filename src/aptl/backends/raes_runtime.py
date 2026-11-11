"""Public RAES planning and one native-evidence runtime owner."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aptl.backends.raes_evidence_acquisition import NativeEvidenceRequest
    from aptl.core.evidence.adapters.sources import WindowedSource
    from aptl.core.evidence.coordinator import AcquisitionResult

from raes_contracts.artifact_requirements import ArtifactAvailabilityContext
from raes_contracts.realization_profiles import PlanProfileAuthority
from raes_contracts.run_scope import PlanScope
from raes_contracts.runtime_state import (
    ApplyResult,
    OperationReceipt,
    RuntimeSnapshot,
)
from raes_processor.compiler import compile_scenario_runtime_model
from raes_processor.models import ExecutionPlan
from raes_processor.planner import plan
from raes_runtime.manager import RuntimeManager as _RaesRuntimeManager
from raes_runtime.registry import RuntimeTarget

from aptl.core.scenario_bundle import ScenarioBundle


def plan_for_target(
    target: RuntimeTarget,
    scenario: object,
    options: AptlPlanningOptions,
) -> ExecutionPlan:
    """Compile and plan once without changing the compiler output.

    Planning reads the target's manifest and profile context but acts on no
    backend, so it needs no runtime owner. The one runtime for the run is
    created for apply.
    """

    parameters = options.parameters
    run_scope = planning_run_scope(
        getattr(target.provisioner, "bundle", None),
        options.run_scope,
        required="backend-materialization-attestation-v1"
        in target.manifest.supported_contract_versions,
    )
    model = compile_scenario_runtime_model(
        scenario,
        parameters=dict(parameters) if parameters is not None else None,
        profile=options.profile,
        profile_authority=options.profile_authority,
    )
    scope = PlanScope(
        target_name=target.name,
        run_id=run_scope.run_id if run_scope is not None else None,
        instantiation_id=(
            run_scope.instantiation_id if run_scope is not None else None
        ),
    )
    execution_plan = plan(
        model,
        target.manifest,
        options.snapshot if options.snapshot is not None else RuntimeSnapshot(),
        scope=scope,
        artifact_availability=options.artifact_availability,
        profile_context=getattr(target.provisioner, "domain_profile_context", None),
    )
    from aptl.backends.raes_participant_runtime import AptlParticipantRuntime

    participant_runtime = getattr(target, "participant_runtime", None)
    if isinstance(participant_runtime, AptlParticipantRuntime):
        execution_plan.diagnostics.extend(
            participant_runtime.autonomous_execution.planning_diagnostics(model)
        )
    return execution_plan


class AptlRuntimeManager(_RaesRuntimeManager):
    """One RAES runtime owner with native materialization evidence capture."""

    # One instance is the run's only runtime owner (OpenRAE/rae#1660).

    def __init__(
        self,
        target: RuntimeTarget,
        *,
        bundle: ScenarioBundle | None = None,
        run_scope: str = "run:default",
        **options: object,
    ) -> None:
        super().__init__(target, run_scope=run_scope, **options)
        self._lilrae_run_id = run_scope.removeprefix("run:")
        self._aptl_bundle = bundle or getattr(target.provisioner, "bundle", None)
        self.native_evidence = None
        from aptl.backends.lilrae_materialization_archive import (
            LilraeMaterializationArchive,
        )
        from aptl.backends.lilrae_runtime_evidence import LilraeRuntimeEvidence

        archive = options.get("materialization_archive")
        if isinstance(archive, LilraeMaterializationArchive):
            self.native_evidence = LilraeRuntimeEvidence(
                archive,
                getattr(target.provisioner, "deployment_backend", None),
                provisioner=target.provisioner,
            )

    def apply(self, execution_plan: ExecutionPlan) -> ApplyResult:
        """Apply with the released limits and retain native evidence."""

        result = super().apply(execution_plan)
        if self.native_evidence is not None:
            self.native_evidence.capture(
                execution_plan, result.snapshot, phase="initial", success=result.success
            )
        return result

    def collect_evidence(
        self,
        request: NativeEvidenceRequest,
        *,
        attempt_id: str,
        sources: Mapping[str, WindowedSource] | None = None,
        trial_body: Callable[[], None] | None = None,
    ) -> AcquisitionResult:
        """Collect for this runtime's run, backend and advertised capabilities.

        The assigned-trial caller owns execution and cleanup. Collection
        finalizes before this call returns, using the existing result contract.
        """
        from aptl.backends.raes_evidence_acquisition import acquire_trial_evidence

        if (
            request.run_id != self._lilrae_run_id
            or request.backend
            is not getattr(self._target.provisioner, "deployment_backend", None)
            or request.capture_selection.registry.observation_projection()
            != self._target.manifest.observation
            or request.plan.plan_digest
            != getattr(
                getattr(self._target.provisioner, "capture_plan", None),
                "plan_digest",
                None,
            )
        ):
            raise ValueError("capture request differs from its runtime owner")
        if trial_body is None and request.window is None:
            raise ValueError("runtime capture requires the requested trial window")
        return acquire_trial_evidence(
            request, attempt_id=attempt_id, sources=sources, trial_body=trial_body
        )

    def refresh_inventory(self, execution_plan: ExecutionPlan) -> ApplyResult:
        """Refresh inventory and capture native evidence for the run."""

        result = super().refresh_inventory(execution_plan)
        if self.native_evidence is not None:
            self.native_evidence.capture(
                execution_plan,
                result.snapshot,
                phase="inventory",
                success=result.success,
            )
        return result

    def evaluate(
        self,
        execution_plan: ExecutionPlan | None = None,
        *,
        idempotency_key: str = "",
        identity: object | None = None,
    ) -> OperationReceipt:
        """Evaluate the plan and capture native evidence for the run."""

        receipt = super().evaluate(
            execution_plan, idempotency_key=idempotency_key, identity=identity
        )
        if self.native_evidence is not None and execution_plan is not None:
            operation = self.get_operation(receipt.operation_id, identity=identity)
            self.native_evidence.capture(
                execution_plan, self.snapshot, phase="evaluation", operation=operation
            )
        return receipt

    def plan(
        self,
        scenario: object,
        snapshot: RuntimeSnapshot | None = None,
        *,
        parameters: dict[str, object] | None = None,
        profile: str | None = None,
        artifact_availability: ArtifactAvailabilityContext | None = None,
        profile_authority: PlanProfileAuthority | None = None,
        run_scope: PlanScope | None = None,
    ) -> ExecutionPlan:
        """Plan against this runtime's committed snapshot."""

        return plan_for_target(
            self._target,
            scenario,
            AptlPlanningOptions(
                snapshot=snapshot if snapshot is not None else self.snapshot,
                parameters=parameters,
                profile=profile,
                artifact_availability=artifact_availability,
                profile_authority=profile_authority,
                run_scope=run_scope or PlanScope(run_id=self._lilrae_run_id),
            ),
        )


from aptl.backends._raes_planning_entry import (
    AptlPlanningOptions,
    planning_run_scope,
    plan_aptl_scenario,
)

__all__ = [
    "AptlPlanningOptions",
    "AptlRuntimeManager",
    "plan_aptl_scenario",
    "plan_for_target",
]
