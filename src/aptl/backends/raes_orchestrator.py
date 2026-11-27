"""APTL RAES orchestration adapter.

This module is the RAES ``Orchestrator`` component on APTL's
``RuntimeTarget``. The RAES runtime owns workflow execution: it walks each
workflow graph, records the portable ``workflow-result-envelope-v1`` and
``workflow-history-event-stream-v1`` state, and dispatches one step at a time
to ``dispatch_step()``.

``start()`` installs the non-workflow orchestration resources as RAES
``SnapshotEntry`` records. It keeps the workflow results and history that the
runtime already recorded. ``dispatch_step()`` runs one step:

- A control step (decision, parallel, join, end, and so on) has no backend
  work, so its response has no outcome.
- A scripted objective step reports the evaluator's current result for its
  objective. A ready result that passed is ``succeeded``; a ready result that
  did not pass is ``failed``. Any other result is an error, because APTL
  cannot report an outcome that it has not observed.
- APTL does not run governed (non-scripted) steps, so it refuses them.

``stop()`` clears orchestration state. Nothing here hardcodes TechVault, a
profile, a compose profile, or a workflow address.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.contracts.workflow_dispatch import (
    WorkflowStepDispatch,
    WorkflowStepResponse,
)
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.evaluation import EvaluationExecutionState, EvaluationResultStatus
from raes_contracts.planning import ChangeAction, OrchestrationPlan, RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry

from aptl.core.trial_readiness import TrialReadinessGate
from aptl.utils.redaction import redact

ORCHESTRATION_ADDRESS = "runtime.apply.orchestration"
_WORKFLOW_RESOURCE_TYPE = "workflow"
_EXECUTABLE_STEP_TYPES = frozenset({"objective", "retry"})

ObjectiveResults = Callable[[], Mapping[str, Mapping[str, object]]]


def _orchestration_diagnostic(code: str, address: str, message: str) -> Diagnostic:
    """Build a redacted orchestration-domain RAES error diagnostic."""
    return Diagnostic(
        code=code,
        domain=RuntimeDomain.ORCHESTRATION.value,
        address=address,
        message=redact(message),
        severity=Severity.ERROR,
    )


def _no_objective_results() -> Mapping[str, Mapping[str, object]]:
    """Return no evaluation results for an orchestrator without an evaluator."""
    return {}


@dataclass
class AptlOrchestrator(object):
    """Orchestration component of APTL's ``full-remote-control-plane`` target."""

    objective_results: ObjectiveResults = field(
        default=_no_objective_results, repr=False
    )
    reporting_manifest: BackendManifest | None = field(default=None, repr=False)
    readiness: TrialReadinessGate | None = field(default=None, repr=False)

    def start(self, plan: object, snapshot: object) -> ApplyResult:
        """Install the non-workflow resources of a RAES orchestration plan."""
        if self.readiness is not None:
            self.readiness.require_live()
        working_snapshot = (
            snapshot if isinstance(snapshot, RuntimeSnapshot) else RuntimeSnapshot()
        )
        if not isinstance(plan, OrchestrationPlan):
            return self._refused(
                working_snapshot,
                "aptl.orchestrator.invalid-plan",
                "APTL orchestrator expected a RAES OrchestrationPlan.",
            )
        if any(op.resource_type == _WORKFLOW_RESOURCE_TYPE for op in plan.operations):
            return self._refused(
                working_snapshot,
                "aptl.orchestrator.workflow-not-dispatched",
                "Workflow steps require RAES runtime dispatch.",
            )

        entries = dict(working_snapshot.entries)
        changed: list[str] = []
        for op in plan.actionable_operations:
            changed.append(op.address)
            if op.action == ChangeAction.DELETE:
                entries.pop(op.address, None)
                continue
            entries[op.address] = SnapshotEntry(
                address=op.address,
                domain=RuntimeDomain.ORCHESTRATION,
                resource_type=op.resource_type,
                payload=op.payload,
                ordering_dependencies=op.ordering_dependencies,
                refresh_dependencies=op.refresh_dependencies,
                status="ready",
            )

        result = ApplyResult(
            success=True,
            snapshot=working_snapshot.with_entries(entries),
            changed_addresses=changed,
        )
        from aptl.backends.lilrae_materialization_reporting import (
            materialization_result,
        )
        from aptl.backends.raes_manifest import create_aptl_manifest

        return materialization_result(
            plan,
            working_snapshot,
            result,
            self.reporting_manifest or create_aptl_manifest(),
        )

    def dispatch_step(self, request: WorkflowStepDispatch) -> WorkflowStepResponse:
        """Run only this step; the RAES runtime selects every successor."""
        outcome = None
        if request.step_type in _EXECUTABLE_STEP_TYPES:
            if request.execution_mode != "scripted":
                raise ValueError(
                    redact(
                        f"APTL does not run {request.execution_mode} workflow step "
                        f"'{request.step_name}'."
                    )
                )
            outcome = self._objective_outcome(request)
        return WorkflowStepResponse(
            dispatch_id=request.dispatch_id,
            dispatch_digest=request.digest,
            outcome=outcome,
            observations=dict(request.observation_digests),
        )

    def status(self) -> dict[str, object]:
        """Return current orchestration status."""
        return {"backend": "aptl"}

    def results(self) -> dict[str, dict[str, object]]:
        """Return no workflow results; the RAES runtime records them."""
        return {}

    def history(self) -> dict[str, list[dict[str, object]]]:
        """Return no workflow history; the RAES runtime records it."""
        return {}

    def stop(self, snapshot: object) -> ApplyResult:
        """Stop orchestration and clear orchestration state."""
        working_snapshot = (
            snapshot if isinstance(snapshot, RuntimeSnapshot) else RuntimeSnapshot()
        )
        retained_entries = {
            address: entry
            for address, entry in working_snapshot.entries.items()
            if entry.domain != RuntimeDomain.ORCHESTRATION
        }
        changed = sorted(set(working_snapshot.entries) - set(retained_entries))
        return ApplyResult(
            success=True,
            snapshot=working_snapshot.with_entries(
                retained_entries,
                orchestration_results={},
                orchestration_history={},
            ),
            changed_addresses=changed,
        )

    def _objective_outcome(self, request: WorkflowStepDispatch) -> str:
        """Report the evaluator's ready result for the step's objective."""
        payload = self.objective_results().get(request.objective_address)
        if payload is None:
            raise ValueError(
                redact(
                    f"Workflow step '{request.step_name}' has no evaluation result "
                    f"for objective '{request.objective_address}'."
                )
            )
        observed = EvaluationExecutionState.from_payload(payload)
        if observed.status is not EvaluationResultStatus.READY or not isinstance(
            observed.passed, bool
        ):
            raise ValueError(
                redact(
                    f"Workflow step '{request.step_name}' objective "
                    f"'{request.objective_address}' has no ready pass or fail result."
                )
            )
        return "succeeded" if observed.passed else "failed"

    @staticmethod
    def _refused(snapshot: RuntimeSnapshot, code: str, message: str) -> ApplyResult:
        """Return a failed apply that leaves the snapshot unchanged."""
        return ApplyResult(
            success=False,
            snapshot=snapshot,
            diagnostics=[
                _orchestration_diagnostic(code, ORCHESTRATION_ADDRESS, message)
            ],
        )
