"""One runtime owner keeps its clock through TechVault native evaluation (#1700)."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.errors import ConflictError
from raes_contracts.planning import EvaluationPlan
from raes_processor.models.time_model import (
    CompiledClock,
    CompiledTimeDomain,
    CompiledTimeModel,
    CompiledTimeProgressionPolicy,
)

from aptl.backends.raes_runtime import AptlRuntimeManager
from tests.techvault.test_raes_native_evidence_truth import (
    _INTERPRETER,
    _plan,
    _record,
)
from tests.test_lilrae_runtime_lifetime import _execution


@pytest.mark.parametrize("native_evidence", [False, True])
def test_single_owner_preserves_clock_through_repeated_evaluation(native_evidence):
    from aptl.backends.raes_evaluator import AptlEvaluator
    from aptl.core.lab import _refresh_required_native_evidence

    target = replace(
        create_stub_target(),
        evaluator=AptlEvaluator(proposition_interpreter=_INTERPRETER),
    )
    time_model = CompiledTimeModel(
        domains=(
            CompiledTimeDomain(
                address="time.domain.study",
                kind="logical",
                tick_period_numerator=1,
                tick_period_denominator=1,
                epoch="run_start",
                visibility="runtime_only",
                description="Study time",
            ),
        ),
        clocks=(
            CompiledClock(
                address="time.clock.study",
                time_domain_address="time.domain.study",
                authority_kind="runtime",
                authority_ref="runtime",
                monotonicity="strict",
                supports_pause=True,
                supports_reset=False,
                supports_jump=False,
                description="Study clock",
            ),
        ),
        progression_policies=(
            CompiledTimeProgressionPolicy(
                address="time.progression-policy.study",
                clock_address="time.clock.study",
                advancement_mode="stepped",
                pacing_numerator=1,
                pacing_denominator=1,
                synchronization_mode="none",
                step_ticks=1,
                drift_bound_ticks=None,
                reset_behavior="unsupported",
                replay_behavior="unsupported",
                description="Study progression",
            ),
        ),
    )
    execution_plan = _execution(
        target,
        evaluation=_plan() if native_evidence else EvaluationPlan(),
        time_model=time_model,
    )
    with AptlRuntimeManager(target) as manager:
        applied = manager.apply(execution_plan)
        assert applied.success, applied.diagnostics
        for index in range(2):
            before = manager.read_time_state()
            if native_evidence:
                outcome = SimpleNamespace(
                    runtime_manager=manager, final_snapshot=manager.snapshot
                )
                failure = _refresh_required_native_evidence(
                    SimpleNamespace(raes_outcome=outcome),
                    SimpleNamespace(target=target, execution_plan=execution_plan),
                    (_record("suricata-local-rule-readiness"),),
                )
                assert failure is None
                assert outcome.runtime_manager is manager
                assert outcome.final_snapshot == manager.snapshot
                assert (
                    manager.snapshot.proposition_truth_results[
                        "evaluation.assertion.suricata-local-rules-ready"
                    ]["assertion_outcome"]
                    == "true"
                )
            else:
                receipt = manager.evaluate(
                    execution_plan, idempotency_key=f"evaluation-{index}"
                )
                assert receipt.accepted, receipt.diagnostics
            assert manager.read_time_state() == before
            with pytest.raises(ConflictError, match="already has a runtime owner"):
                AptlRuntimeManager(target)
            advanced = manager.advance_time("time.clock.study", ticks=1)
            assert advanced.success, advanced.diagnostics
            assert manager.read_time_state() != before
