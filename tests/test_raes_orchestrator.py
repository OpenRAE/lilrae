"""Tests for the APTL RAES orchestration adapter.

The RAES runtime walks each workflow graph and dispatches one step at a time
to ``AptlOrchestrator.dispatch_step``.
"""

from textwrap import dedent

import pytest
from raes_contracts.contracts.workflow_dispatch import WorkflowStepDispatch
from raes_contracts.evaluation import EvaluationExecutionState, EvaluationResultStatus
from raes_contracts.planning import (
    ChangeAction,
    OrchestrationOp,
    OrchestrationPlan,
    RuntimeDomain,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry
from raes_contracts.versions import WORKFLOW_DISPATCH_CONTRACTS
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes.parser import parse_sdl

from aptl.backends.raes_manifest import create_aptl_manifest
from aptl.backends.raes_orchestrator import AptlOrchestrator

_OBJECTIVE = "evaluation.objective.validate"
_DIGEST = "sha256:" + "0" * 64

_WORKFLOW_SCENARIO = dedent(
    """
    name: orchestrator-test
    nodes:
      vm:
        type: compute
        os: linux
        resources: {ram: 1 gib, cpu: 1}
        conditions: {health: ops}
        roles: {ops: operator}
    conditions:
      health:
        proposition: health
        command: /bin/true
        interval: 15
    entities:
      blue: {role: blue}
    propositions:
      health:
        description: The governed health observation is true for the addressed scenario subject.
        subjects: [nodes.vm]
        basis: observed_state
        predicate:
          kind: boolean
          property: health
          semantic_ref: "urn:aces:observable:health"
          operator: equals
          expected: true
        quantifier: all
        evidence_requirements: [objective-truth-evidence]
    assertions:
      health:
        proposition: health
        role: postcondition
        polarity: positive
    evidence_requirements:
      objective-truth-evidence:
        description: Capture evidence used to decide authored proposition assertions.
        source_refs: [nodes.vm]
        scope: authored objective assertion evaluation
        boundary_kind: assertion_evaluation
        channel: log
        artifact_role: proposition_truth_evidence
        media_types: [application/json]
        sensitivity: plain
        redaction: redact_secrets
        integrity: checksum
        retention: study_lifetime
        loss_disclosure: required
    objectives:
      validate:
        owner: blue
        success: {assertions: [health]}
    workflows:
      response:
        start: run
        steps:
          run:
            type: objective
            objective: validate
            on_success: finish
          finish: {type: end}
    """
)


def _execution_plan():
    scenario = parse_sdl(_WORKFLOW_SCENARIO)
    return plan(compile_runtime_model(scenario), create_aptl_manifest())


def _dispatch(step_type="objective", **overrides):
    fields = {
        "dispatch_id": "dispatch-1",
        "program_digest": _DIGEST,
        "root_operation_id": "root-1",
        "invocation_id": "invocation-1",
        "workflow_address": "orchestration.workflow.response",
        "branch_id": "main",
        "step_name": "run",
        "step_type": step_type,
        "attempt": 1,
        "predecessor_revision": 0,
        "objective_address": _OBJECTIVE if step_type == "objective" else "",
    }
    fields.update(overrides)
    return WorkflowStepDispatch(**fields)


def _evaluation(status, passed=None):
    return EvaluationExecutionState(
        resource_type="objective",
        run_id="evaluation-run",
        status=status,
        observed_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        passed=passed,
    ).to_payload()


def _orchestrator(results=None):
    return AptlOrchestrator(objective_results=lambda: dict(results or {}))


def _op(address, *, resource_type="event", action=ChangeAction.CREATE):
    return OrchestrationOp(
        action=action,
        address=address,
        resource_type=resource_type,
        payload={"name": address},
    )


def test_manifest_declares_runtime_workflow_step_dispatch():
    manifest = create_aptl_manifest()

    assert set(WORKFLOW_DISPATCH_CONTRACTS) <= set(manifest.supported_contract_versions)
    assert not [d for d in _execution_plan().diagnostics if d.is_error]


@pytest.mark.parametrize(("passed", "outcome"), [(True, "succeeded"), (False, "failed")])
def test_objective_step_reports_the_ready_evaluation_result(passed, outcome):
    request = _dispatch()
    orchestrator = _orchestrator(
        {_OBJECTIVE: _evaluation(EvaluationResultStatus.READY, passed)}
    )

    response = orchestrator.dispatch_step(request)

    assert response.outcome == outcome
    response.require_dispatch(request)


def test_control_step_reports_no_outcome_and_echoes_observations():
    request = _dispatch(
        "decision",
        step_name="choose",
        observation_addresses=(_OBJECTIVE,),
        observation_digests={_OBJECTIVE: _DIGEST},
    )

    response = _orchestrator().dispatch_step(request)

    assert response.outcome is None
    assert response.observations == {_OBJECTIVE: _DIGEST}
    response.require_dispatch(request)


@pytest.mark.parametrize(
    "results",
    [
        {},
        {_OBJECTIVE: _evaluation(EvaluationResultStatus.RUNNING)},
        {_OBJECTIVE: _evaluation(EvaluationResultStatus.FAILED)},
    ],
    ids=["missing", "running", "evaluation-failed"],
)
def test_objective_step_without_a_ready_result_is_an_error(results):
    with pytest.raises(ValueError, match="evaluation result|ready pass or fail"):
        _orchestrator(results).dispatch_step(_dispatch())


def test_governed_step_is_refused():
    orchestrator = _orchestrator(
        {_OBJECTIVE: _evaluation(EvaluationResultStatus.READY, True)}
    )

    with pytest.raises(ValueError, match="does not run objective workflow step"):
        orchestrator.dispatch_step(_dispatch(execution_mode="objective"))


def test_start_refuses_workflow_resources():
    result = _orchestrator().start(_execution_plan().orchestration, RuntimeSnapshot())

    assert result.success is False
    assert [d.code for d in result.diagnostics] == [
        "aptl.orchestrator.workflow-not-dispatched"
    ]


def test_start_installs_resources_and_keeps_runtime_workflow_records():
    workflow = "orchestration.workflow.response"
    base = RuntimeSnapshot(
        entries={
            "provision.node.vm": SnapshotEntry(
                address="provision.node.vm",
                domain=RuntimeDomain.PROVISIONING,
                resource_type="node",
                payload={"name": "vm"},
            )
        },
        orchestration_results={workflow: {"workflow_status": "running"}},
        orchestration_history={workflow: [{"event_type": "workflow_started"}]},
    )
    address = "orchestration.event.kickoff"

    result = _orchestrator().start(
        OrchestrationPlan(resources={}, operations=[_op(address)]), base
    )

    assert isinstance(result, ApplyResult)
    assert result.success is True
    assert result.changed_addresses == [address]
    assert result.snapshot.entries[address].domain == RuntimeDomain.ORCHESTRATION
    assert "provision.node.vm" in result.snapshot.entries
    assert result.snapshot.orchestration_results == base.orchestration_results
    assert result.snapshot.orchestration_history == base.orchestration_history


def test_start_handles_delete_operation():
    address = "orchestration.event.gone"
    base = RuntimeSnapshot(
        entries={
            address: SnapshotEntry(
                address=address,
                domain=RuntimeDomain.ORCHESTRATION,
                resource_type="event",
                payload={"name": address},
            )
        }
    )

    result = _orchestrator().start(
        OrchestrationPlan(
            resources={}, operations=[_op(address, action=ChangeAction.DELETE)]
        ),
        base,
    )

    assert result.success is True
    assert address not in result.snapshot.entries
    assert result.changed_addresses == [address]


def test_start_rejects_non_orchestration_plan():
    result = _orchestrator().start(object(), RuntimeSnapshot())

    assert result.success is False
    assert [d.code for d in result.diagnostics] == ["aptl.orchestrator.invalid-plan"]


def test_runtime_owns_workflow_results_and_history():
    orchestrator = _orchestrator()

    assert orchestrator.results() == {}
    assert orchestrator.history() == {}
    assert orchestrator.status() == {"backend": "aptl"}


def test_stop_clears_orchestration_state():
    address = "orchestration.event.kickoff"
    base = RuntimeSnapshot(
        entries={
            address: SnapshotEntry(
                address=address,
                domain=RuntimeDomain.ORCHESTRATION,
                resource_type="event",
                payload={"name": address},
            )
        },
        orchestration_results={"orchestration.workflow.response": {"x": 1}},
    )

    stopped = _orchestrator().stop(base)

    assert stopped.success is True
    assert stopped.snapshot.entries == {}
    assert stopped.snapshot.orchestration_results == {}
    assert stopped.snapshot.orchestration_history == {}
    assert stopped.changed_addresses == [address]
