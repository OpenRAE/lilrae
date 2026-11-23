"""Readiness enforcement around the existing RAES installed trial services."""

from dataclasses import dataclass, field

from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_contracts.trial_unit import TrialUnitRequest
from raes_runtime.runtime_trial_services import (
    TrialCaptureObservation,
    TrialCleanupObservation,
    TrialConfigurationObservation,
    TrialExecutionObservation,
    TrialObservation,
    TrialRuntimeServices,
)

from aptl.backends.readiness import TrialReadiness


@dataclass
class ReadinessTrialServices:
    """Keep native cessation/evidence and refuse a false successful trial.

    RAES still owns configuration, execution, capture, stop and cleanup. A
    workload observer may report cessation after a rejected apply. Its success
    alone cannot override a required readiness refusal.
    """

    services: TrialRuntimeServices
    readiness: TrialReadiness
    _original_execution: dict[str, TrialExecutionObservation] = field(
        default_factory=dict, init=False
    )

    def admit(self, request: TrialUnitRequest) -> None:
        self.services.admit(request)

    def configure(
        self, request: TrialUnitRequest, snapshot: RuntimeSnapshot
    ) -> tuple[ApplyResult, TrialConfigurationObservation]:
        self.readiness.require_prepared(request)
        if not request.provisioning_plan.operations:
            self.readiness.require_live()
        return self.services.configure(request, snapshot)

    def observe(
        self, request: TrialUnitRequest, snapshot: RuntimeSnapshot
    ) -> TrialExecutionObservation:
        observed = self.services.observe(request, snapshot)
        if (
            observed.state == "succeeded"
            and observed.ceased
            and not self.readiness.execution_ready
        ):
            self._original_execution[request.execution_attempt_id] = (
                observed.model_copy(deep=True)
            )
            return observed.model_copy(update={"state": "failed"})
        return observed

    def capture(
        self, request: TrialUnitRequest, snapshot: RuntimeSnapshot
    ) -> tuple[ApplyResult, TrialCaptureObservation]:
        return self.services.capture(request, snapshot)

    def cleanup(
        self, request: TrialUnitRequest, outcome: str, snapshot: RuntimeSnapshot
    ) -> tuple[ApplyResult, TrialCleanupObservation]:
        return self.services.cleanup(request, outcome, snapshot)

    def stop(
        self, request: TrialUnitRequest, cause: str, snapshot: RuntimeSnapshot
    ) -> ApplyResult:
        return self.services.stop(request, cause, snapshot)

    def verify(self, request: TrialUnitRequest, observation: TrialObservation) -> None:
        original = self._original_execution.get(request.execution_attempt_id)
        if isinstance(observation, TrialExecutionObservation) and original is not None:
            projected = original.model_copy(update={"state": "failed"})
            if observation.model_dump(mode="json") == projected.model_dump(mode="json"):
                self.services.verify(request, original)
                return
        self.services.verify(request, observation)
