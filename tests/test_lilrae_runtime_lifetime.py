"""One RAES runtime retains time, evidence and exclusive run ownership."""

from dataclasses import replace

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.errors import OperationalError
from raes_contracts.planning import EvaluationPlan
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.models import RuntimeModel
from aptl.backends.raes_runtime import AptlRuntimeManager


def _execution(target, *, evaluation=None, snapshot=None, time_model=None):
    """Keep the original compiled context required by public evidence refresh."""
    from raes_processor.models.resources import PropositionRuntime, AssertionRuntime
    from raes_processor.planner import plan
    from raes_contracts.planning import PlanScope

    selected = EvaluationPlan() if evaluation is None else evaluation
    model = RuntimeModel(scenario_name="native-evidence-refresh")
    for operation in selected.operations:
        payload = dict(operation.payload)
        payload.setdefault("spec", {})
        cls = (
            PropositionRuntime
            if operation.resource_type == "proposition"
            else AssertionRuntime
        )
        resource = cls(address=operation.address, **payload)
        collection = (
            model.propositions
            if operation.resource_type == "proposition"
            else model.assertions
        )
        collection[resource.address] = resource
    if time_model is not None:
        model = replace(model, time_model=time_model)
    result = plan(
        model,
        target.manifest,
        snapshot or RuntimeSnapshot(),
        scope=PlanScope(target_name=target.name),
    )
    assert result.is_valid, result.diagnostics
    return result


def test_closed_owner_rejects_later_evaluation():
    target = create_stub_target()
    manager = AptlRuntimeManager(target)
    execution = _execution(target, evaluation=EvaluationPlan())
    manager.close()
    with pytest.raises(OperationalError, match="closed"):
        manager.evaluate(execution)
    with AptlRuntimeManager(target) as replacement:
        assert replacement.snapshot == RuntimeSnapshot()
