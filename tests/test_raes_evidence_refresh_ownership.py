"""The native evidence refresh owns the target only after the start's manager releases it."""

from __future__ import annotations

import importlib
from dataclasses import replace
from types import SimpleNamespace

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.planning import OrchestrationPlan, ProvisioningPlan, RuntimeDomain
from raes_contracts.runtime_state import OperationState, RuntimeSnapshot
from raes_processor.models import ExecutionPlan, RuntimeModel

from aptl.backends import raes_evaluator
from aptl.backends.raes_evaluator import AptlEvaluator, refresh_evidence_truth
from aptl.backends.raes_planning_compat import AptlRuntimeManager
from aptl.core import lab
from tests.test_raes_native_evidence_truth import _INTERPRETER, _plan, _record


def _target_and_plan():
    evaluator = AptlEvaluator(proposition_interpreter=_INTERPRETER)
    target = replace(create_stub_target(), evaluator=evaluator)
    execution_plan = ExecutionPlan(
        target_name=target.name,
        manifest=target.manifest,
        base_snapshot=RuntimeSnapshot(),
        scenario_name="native-evidence-refresh",
        model=RuntimeModel(scenario_name="native-evidence-refresh"),
        provisioning=ProvisioningPlan(),
        orchestration=OrchestrationPlan(),
        evaluation=_plan(),
        observation_owner=RuntimeDomain.PROVISIONING,
    )
    return target, execution_plan


def _records():
    return (_record("suricata-local-rule-readiness"),)


def _ownership():
    return importlib.import_module("aptl.backends._raes_evidence_refresh_ownership")


def test_raes_refuses_a_refresh_while_the_start_manager_owns_the_target():
    """The premise: RAES admits one live owner per target component."""

    target, execution_plan = _target_and_plan()
    start_manager = AptlRuntimeManager(target)
    try:
        with pytest.raises(RuntimeError, match="runtime owner"):
            refresh_evidence_truth(
                target=target,
                execution_plan=execution_plan,
                snapshot=RuntimeSnapshot(),
                evidence_records=_records(),
            )
    finally:
        start_manager.close()


def test_lab_start_refreshes_native_evidence_after_a_successful_apply():
    """The start's manager is still alive after apply; the refresh must not fail on it."""

    target, execution_plan = _target_and_plan()
    outcome = SimpleNamespace(
        runtime_manager=AptlRuntimeManager(target), final_snapshot=RuntimeSnapshot()
    )
    context = SimpleNamespace(raes_outcome=outcome)
    admitted = SimpleNamespace(target=target, execution_plan=execution_plan)

    failure = lab._refresh_required_native_evidence(context, admitted, _records())

    try:
        assert failure is None
        assert sorted(outcome.final_snapshot.proposition_truth_results) == [
            "evaluation.assertion.suricata-local-rules-ready"
        ]
        assert outcome.runtime_manager.snapshot == outcome.final_snapshot
    finally:
        outcome.runtime_manager.close()


def test_released_owner_is_replaced_by_one_holding_the_refreshed_truth():
    """After the refresh, later steps keep a live owner of the refreshed snapshot."""

    target, execution_plan = _target_and_plan()
    start_manager = AptlRuntimeManager(target)
    outcome = SimpleNamespace(runtime_manager=start_manager)

    refresh = _ownership().refresh_evidence_truth_with_start_owner(
        outcome,
        target=target,
        execution_plan=execution_plan,
        snapshot=RuntimeSnapshot(),
        evidence_records=_records(),
    )

    try:
        assert refresh.status is OperationState.SUCCEEDED
        assert outcome.runtime_manager is not start_manager
        assert outcome.runtime_manager.snapshot == refresh.snapshot
    finally:
        outcome.runtime_manager.close()


def test_owner_that_does_not_close_fails_the_refresh_without_running_it(monkeypatch):
    """A manager that keeps ownership yields a failed refresh with its own reason."""

    class _StuckManager:
        def close(self):
            raise RuntimeError("still busy")

    def _must_not_run(**_kwargs):
        raise AssertionError("the refresh ran while the start still owned the target")

    ownership = _ownership()
    monkeypatch.setattr(raes_evaluator, "refresh_evidence_truth", _must_not_run)
    stuck = _StuckManager()
    outcome = SimpleNamespace(runtime_manager=stuck)

    refresh = ownership.refresh_evidence_truth_with_start_owner(
        outcome,
        target=object(),
        execution_plan=object(),
        snapshot=RuntimeSnapshot(),
        evidence_records=(),
    )

    assert refresh.status is OperationState.FAILED
    assert [d.code for d in refresh.diagnostics] == [
        "aptl.evaluator.start-runtime-owner-not-released"
    ]
    assert "still busy" in refresh.diagnostics[0].message
    assert outcome.runtime_manager is stuck
