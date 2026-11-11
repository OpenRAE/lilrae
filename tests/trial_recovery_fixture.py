"""Public assigned-entry composition using the existing installed test owners."""

from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime

from raes_contracts.assigned_trial import TrialOutcomeModel
from raes_contracts.trial_unit import TrialUnitRequest
from raes_backend_protocols.capabilities import BackendManifest
from raes_processor.trial_scheduler import plan_batch_schedule
from raes_processor.trial_realization import TrialRealizationInputs
from raes_runtime import RuntimeControlPlane
from raes_runtime.control_plane_store import LocalControlPlaneStore
from raes_runtime.runtime_assigned_trial import AssignedTrial

from aptl.backends.trial_services import ReadinessTrialServices
from aptl.backends.trial_serving import (
    DockerTrialPlacement,
    LilraeTrialUnit,
    TrialOutcomeReporting,
)
from aptl.core.correlation.clock import FixedClockProvider
from aptl.core.runstore import LocalRunStore
from tests.cleanup_runtime_fixture import Services, runtime_inputs, target_for
from tests.test_trial_serving import PlacementBackend
from tests.trial_readiness_fixture import readiness_for


class OriginalOutcomeVerifier:
    def __init__(self, services: Services):
        self.services = services
        self.binding: AssignedTrial | None = None

    def verify_outcome(self, request: TrialUnitRequest, outcome: TrialOutcomeModel) -> None:
        assert self.binding is not None
        assert self.binding.request == request
        assert self.binding.outcome(identity="worker-437") == outcome
        for fact in outcome.facts:
            self.services.verify(request, fact.observation)


@dataclass(frozen=True)
class AssignedServing:
    handler: LilraeTrialUnit
    binding: AssignedTrial
    coordinator: RuntimeControlPlane
    worker: RuntimeControlPlane
    experiment_id: str
    services: Services
    clock: FixedClockProvider
    inputs: TrialRealizationInputs
    manifest: BackendManifest
    verifier: OriginalOutcomeVerifier

    def records(self):
        return self.coordinator.experiment_records(self.experiment_id)

    def cancellation(self):
        self.coordinator.cancel_experiment(self.experiment_id)
        return self.coordinator.assigned_trial_control(
            self.experiment_id, self.binding.assignment_digest
        )


@contextmanager
def assigned_serving(tmp_path, *, pending=True, cleanup_fails=False, durable=False):
    inputs, manifest = runtime_inputs(tmp_path)
    target = target_for(manifest)
    services = Services(tmp_path, pending=pending, cleanup_fails=cleanup_fails)
    clock = FixedClockProvider(measurement_time="2026-11-03T22:00:00Z")
    backend = PlacementBackend(tmp_path)
    state = tmp_path / "placement-state"
    state.mkdir()
    readiness = readiness_for(
        inputs, target, LocalRunStore(tmp_path / "runs"), clock, tmp_path
    )
    installed = ReadinessTrialServices(services, readiness)
    verifier = OriginalOutcomeVerifier(services)
    with (
        RuntimeControlPlane(
            target_for(manifest), wall_clock=lambda: datetime.fromisoformat(clock.now())
        ) as coordinator,
        RuntimeControlPlane(
            target, wall_clock=lambda: datetime.fromisoformat(clock.now()),
            store=LocalControlPlaneStore(tmp_path / "control/worker") if durable else None,
        ) as worker,
    ):
        experiment_id = coordinator.admit_experiment(
            inputs,
            services=Services(tmp_path / "coordinator"),
            outcome_verifier=verifier,
        )
        entry = plan_batch_schedule(inputs.plan).entries[0]
        assignment = coordinator.assign_trial(
            experiment_id, entry.plan_entry_id, owner_id="worker-437"
        )
        binding = worker.bind_assigned_trial(
            assignment, inputs, services=installed, identity="worker-437",
            store_factory=(lambda run_id: LocalControlPlaneStore(tmp_path / "control/runs" / run_id)) if durable else None,
        )
        verifier.binding = binding
        cleanup = services.cleanups[binding.request.execution_attempt_id]
        handler = LilraeTrialUnit(
            binding,
            cleanup,
            DockerTrialPlacement(backend, state),
            assignment.target_scope,
            TrialOutcomeReporting(coordinator, experiment_id, lambda request, result: {}),
            readiness=readiness,
        )
        try:
            yield AssignedServing(handler, binding, coordinator, worker, experiment_id, services, clock, inputs, manifest, verifier)
        finally:
            readiness.close()


@contextmanager
def restarted_worker(case, tmp_path):
    """Reopen both original RAES SQLite stores with fresh installed owners."""
    assignment = case.binding.assignment
    case.worker.close()
    case.handler.readiness.close()
    target = target_for(case.manifest)
    readiness = readiness_for(
        case.inputs, target, case.handler.cleanup.store, case.clock, tmp_path,
    )
    with RuntimeControlPlane(
        target, store=LocalControlPlaneStore(tmp_path / "control/worker"),
        wall_clock=lambda: datetime.fromisoformat(case.clock.now()),
    ) as worker:
        binding = worker.bind_assigned_trial(
            assignment, case.inputs,
            services=ReadinessTrialServices(case.services, readiness), identity="worker-437",
            store_factory=lambda run_id: LocalControlPlaneStore(tmp_path / "control/runs" / run_id),
        )
        case.verifier.binding = binding
        handler = replace(
            case.handler, runtime_unit=binding, readiness=readiness,
            cleanup=case.services.cleanups[binding.request.execution_attempt_id],
        )
        try:
            yield replace(case, binding=binding, handler=handler, worker=worker)
        finally:
            readiness.close()
