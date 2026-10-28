"""Exclusive RAES ownership across temporary control-plane phases."""

from dataclasses import replace
from types import SimpleNamespace

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


def _run_phase(manager, body=None, **options):
    """Exercise one complete public handoff, including its shutdown."""
    with manager.control_plane(**options) as control_plane:
        if body is not None:
            body(control_plane)


@pytest.mark.parametrize("native_evidence", [False, True])
def test_handoff_preserves_initialized_time_across_repeated_phases(native_evidence):
    from aptl.backends.raes_evaluator import AptlEvaluator
    from aptl.core.lab import _refresh_required_native_evidence
    from tests.test_raes_native_evidence_truth import _INTERPRETER, _plan, _record

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
    execution_plan = ExecutionPlan(
        target_name=target.name,
        manifest=target.manifest,
        base_snapshot=RuntimeSnapshot(),
        scenario_name="handoff",
        model=RuntimeModel(scenario_name="handoff", time_model=time_model),
        provisioning=ProvisioningPlan(),
        orchestration=OrchestrationPlan(),
        evaluation=_plan() if native_evidence else EvaluationPlan(),
        observation_owner=RuntimeDomain.PROVISIONING,
    )
    with AptlRuntimeManager(target) as manager:
        applied = manager.apply(execution_plan)
        assert applied.success, applied.diagnostics
        for _ in range(2):
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
                assert manager.snapshot.proposition_truth_results[
                    "evaluation.assertion.suricata-local-rules-ready"
                ]["assertion_outcome"] == "true"
            else:
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


def test_handoff_adopts_the_phase_snapshot_before_reacquiring_ownership(monkeypatch):
    from aptl.backends import _lilrae_runtime_handoff as handoff

    target = create_stub_target()
    snapshot = RuntimeSnapshot(metadata={"phase": "governed"})
    original_claim = handoff.RuntimeResourceClaim

    def acquire(manager, claimed_target):
        # The next admitted manager call must see the governed phase's cut.
        assert manager.snapshot == snapshot
        return original_claim(manager, claimed_target)

    monkeypatch.setattr(handoff, "RuntimeResourceClaim", acquire)
    with AptlRuntimeManager(target) as manager:
        with manager.control_plane(
            snapshot_transform=lambda previous: replace(
                previous, metadata=snapshot.metadata
            )
        ):
            pass
        assert manager.snapshot == snapshot


def test_failed_manager_drain_does_not_open_a_control_plane(monkeypatch):
    target = create_stub_target()
    with AptlRuntimeManager(target) as manager:
        with monkeypatch.context() as patch:
            def fail_close():
                raise TimeoutError("runtime manager clock driver remains active")

            patch.setattr(manager, "close", fail_close)
            with pytest.raises(TimeoutError, match="clock driver remains active"):
                _run_phase(manager)

        with pytest.raises(RuntimeError, match="already has a runtime owner"):
            AptlRuntimeManager(target)


def test_control_plane_failure_closes_both_owners():
    target = create_stub_target()
    failure = ValueError("phase failed")

    def fail_body(_control_plane):
        raise failure

    with AptlRuntimeManager(target) as manager:
        with pytest.raises(ValueError, match="phase failed"):
            _run_phase(manager, fail_body)

        with pytest.raises(RuntimeError, match="closed"):
            manager.read_time_state()
        # No abandoned temporary claim prevents a clean subsequent attempt.
        AptlRuntimeManager(target).close()


def test_closed_manager_cannot_start_another_handoff():
    target = create_stub_target()
    manager = AptlRuntimeManager(target)
    manager.close()

    with pytest.raises(RuntimeError, match="runtime manager is closed"):
        _run_phase(manager)

    AptlRuntimeManager(target).close()


def test_failed_control_plane_construction_leaves_no_owner():
    from raes_runtime.control_plane_store_memory import InMemoryControlPlaneStore

    target = create_stub_target()
    store = InMemoryControlPlaneStore()
    with AptlRuntimeManager(target) as manager:
        with pytest.raises(ValueError, match="initial_snapshot cannot be combined"):
            _run_phase(manager, store=store)

        with pytest.raises(RuntimeError, match="closed"):
            manager.read_time_state()
        AptlRuntimeManager(target).close()


def test_clock_restart_failure_keeps_the_manager_closed(monkeypatch):
    target = create_stub_target()
    with AptlRuntimeManager(target) as manager:
        monkeypatch.setattr(manager, "_start_participant_clock_driver", lambda: False)
        with pytest.raises(RuntimeError, match="clock driver could not resume"):
            _run_phase(manager)

        with pytest.raises(RuntimeError, match="closed"):
            manager.read_time_state()
        AptlRuntimeManager(target).close()


def test_control_plane_close_failure_never_resumes_the_manager(monkeypatch):
    target = create_stub_target()
    with AptlRuntimeManager(target) as manager:
        original_close = None

        def fail_close():
            raise TimeoutError("runtime drain has unresolved external calls")

        def inject_close_failure(control_plane):
            nonlocal original_close
            original_close = control_plane.close
            monkeypatch.setattr(control_plane, "close", fail_close)

        try:
            with pytest.raises(TimeoutError, match="unresolved external calls"):
                _run_phase(manager, inject_close_failure)

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

        def retain_unresolved_claim(phase):
            nonlocal control_plane
            control_plane = phase
            monkeypatch.setattr(
                phase,
                "_release_runtime_resources",
                lambda: phase._resource_claim.release(unresolved=True),
            )

        try:
            with pytest.raises(RuntimeError, match="already has a runtime owner"):
                _run_phase(manager, retain_unresolved_claim)

            with pytest.raises(RuntimeError, match="closed"):
                manager.read_time_state()
        finally:
            if control_plane is not None:
                control_plane._resource_claim.release()
