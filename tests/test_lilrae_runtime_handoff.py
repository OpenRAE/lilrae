"""Exclusive RAES ownership across temporary control-plane phases."""

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.planning import (
    EvaluationPlan,
    OrchestrationPlan,
    ProvisioningPlan,
    RuntimeDomain,
)
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.models import ExecutionPlan, RuntimeModel
from raes_processor.models.time_model import (
    CompiledClock,
    CompiledTimeDomain,
    CompiledTimeModel,
    CompiledTimeProgressionPolicy,
)

from aptl.backends.raes_planning_compat import AptlRuntimeManager


def test_handoff_preserves_initialized_time_across_repeated_phases():
    target = create_stub_target()
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
    execution_plan = ExecutionPlan(
        target_name=target.name,
        manifest=target.manifest,
        base_snapshot=RuntimeSnapshot(),
        scenario_name="handoff",
        model=RuntimeModel(scenario_name="handoff", time_model=time_model),
        provisioning=ProvisioningPlan(),
        orchestration=OrchestrationPlan(),
        evaluation=EvaluationPlan(),
        observation_owner=RuntimeDomain.PROVISIONING,
    )
    with AptlRuntimeManager(target) as manager:
        applied = manager.apply(execution_plan)
        assert applied.success, applied.diagnostics
        for _ in range(2):
            before = manager.read_time_state()
            with manager.control_plane() as control_plane:
                assert control_plane.snapshot.time_model_state == before
            assert manager.read_time_state() == before
            advanced = manager.advance_time("time.clock.study", ticks=1)
            assert advanced.success, advanced.diagnostics
            assert manager.read_time_state() != before


def test_handoff_excludes_another_owner_and_resumes_the_same_snapshot():
    target = create_stub_target()
    snapshot = RuntimeSnapshot(metadata={"run": "handoff"})
    with AptlRuntimeManager(target, initial_snapshot=snapshot) as manager:
        with manager.control_plane() as control_plane:
            assert control_plane.snapshot == snapshot
            with pytest.raises(RuntimeError, match="closed"):
                manager.read_time_state()
            with pytest.raises(RuntimeError, match="already has a runtime owner"):
                AptlRuntimeManager(target)

        assert manager.snapshot == snapshot
        with pytest.raises(RuntimeError, match="closed"):
            control_plane.get_snapshot()
        with pytest.raises(RuntimeError, match="already has a runtime owner"):
            AptlRuntimeManager(target)
        # The call passes the ownership guard and reaches time validation.
        with pytest.raises(ValueError, match="no initialized shared-time model"):
            manager.read_time_state()


def test_failed_manager_drain_does_not_open_a_control_plane(monkeypatch):
    target = create_stub_target()
    with AptlRuntimeManager(target) as manager:
        with monkeypatch.context() as patch:
            def fail_close():
                raise TimeoutError("runtime manager clock driver remains active")

            patch.setattr(manager, "close", fail_close)
            with pytest.raises(TimeoutError, match="clock driver remains active"):
                with manager.control_plane():
                    pytest.fail("handoff admitted work before the manager drained")

        with pytest.raises(RuntimeError, match="already has a runtime owner"):
            AptlRuntimeManager(target)


def test_control_plane_failure_closes_both_owners():
    target = create_stub_target()
    with AptlRuntimeManager(target) as manager:
        with pytest.raises(ValueError, match="phase failed"):
            with manager.control_plane():
                raise ValueError("phase failed")

        with pytest.raises(RuntimeError, match="closed"):
            manager.read_time_state()
        # No abandoned temporary claim prevents a clean subsequent attempt.
        AptlRuntimeManager(target).close()


def test_control_plane_close_failure_never_resumes_the_manager(monkeypatch):
    target = create_stub_target()
    with AptlRuntimeManager(target) as manager:
        original_close = None
        try:
            with pytest.raises(TimeoutError, match="unresolved external calls"):
                with manager.control_plane() as control_plane:
                    original_close = control_plane.close

                    def fail_close():
                        raise TimeoutError("runtime drain has unresolved external calls")

                    monkeypatch.setattr(control_plane, "close", fail_close)

            with pytest.raises(RuntimeError, match="closed"):
                manager.read_time_state()
            with pytest.raises(RuntimeError, match="already has a runtime owner"):
                AptlRuntimeManager(target)
        finally:
            if original_close is not None:
                original_close()


def test_unresolved_control_plane_claim_prevents_manager_reacquisition(monkeypatch):
    target = create_stub_target()
    with AptlRuntimeManager(target) as manager:
        control_plane = None
        try:
            with pytest.raises(RuntimeError, match="already has a runtime owner"):
                with manager.control_plane() as control_plane:
                    monkeypatch.setattr(
                        control_plane,
                        "_release_runtime_resources",
                        lambda: control_plane._resource_claim.release(unresolved=True),
                    )

            with pytest.raises(RuntimeError, match="closed"):
                manager.read_time_state()
        finally:
            if control_plane is not None:
                control_plane._resource_claim.release()
