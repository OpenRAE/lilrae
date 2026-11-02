"""Check RAE's native settlement and trial reporting contracts in isolation.

These comparisons diagnose the fixture used by issue #1416. They do not
reclassify native effects or assert that an action verdict proves cessation.
"""

from dataclasses import replace

import pytest
from raes_contracts.runtime_state import OperationState
from raes_runtime.runtime_trial_services import TrialExecutionObservation
from raes_runtime.runtime_trial_unit import TrialPending

from aptl.backends.trial_serving import report_trial_outcomes
from aptl.core.trial_ownership import TRIAL_FENCE
from tests.test_trial_serving import serving


def action_results(snapshot):
    return [
        event["action_result"]
        for history in snapshot.participant_behavior_history.values()
        for event in history
        if event.get("action_result") is not None
    ]


@pytest.mark.parametrize("failure", ["timeout", "refusal"])
@pytest.mark.parametrize("policy", ["stop", "continue"])
@pytest.mark.parametrize("entry_index", range(8))
def test_native_policy_does_not_imply_the_same_trial_settlement(
    tmp_path, policy, entry_index, failure
):
    with serving(
        tmp_path,
        native_policy=policy,
        entry_index=entry_index,
        native_refusal=failure == "refusal",
    ) as (
        handler,
        request,
        services,
        runtime,
        experiment_id,
    ):
        from tests.trial_reporting_fixture import RecordingArchive

        archive = RecordingArchive()
        delivered = []

        def metadata(request, result):
            delivered.append(result)
            return {}

        unit = handler.runtime_unit.unit
        handler = replace(
            handler,
            runtime_unit=unit,
            reporting=replace(handler.reporting, metadata=metadata, archive=archive),
        )
        if policy == "stop":
            with pytest.raises(TrialPending):
                handler.execute_trial(request)
            snapshot = unit.run.snapshot
            operations = unit.run._store.load_records()
            unresolved = [
                r
                for r in operations.values()
                if r.status.state is OperationState.INDETERMINATE
            ]
            assert len(unresolved) == 1
            assert unresolved[0].invocation.consumed
            assert unresolved[0].invocation.reserved
            assert services.events == ["configure"]
            assert (tmp_path / TRIAL_FENCE).exists()
        else:
            result = handler.execute_trial(request)
            snapshot = result.execution_snapshot
            assert services.events == ["configure", "capture", "cleanup"]
            # This success/cessation observation comes from the fixture owner,
            # which always reports it. It is not inferred by RAE from an action.
            assert result.cleanup_receipt.trial_outcome == "succeeded"

        assert delivered
        assert (delivered[-1] is None) == (policy == "stop")
        assert request.run_id in archive.sources
        assert any(run.run_id == request.run_id for run in archive.runs.values())
        actions = action_results(snapshot)
        assert len(actions) == 2
        red = [
            a for a in actions if a["participant_address"] == "participant.behavior.red"
        ]
        blue = [
            a
            for a in actions
            if a["participant_address"] == "participant.behavior.blue"
        ]
        assert len(red) == len(blue) == 1
        assert red[0]["status"] == "failed"
        assert red[0]["failure_class"] == (
            "authority_denied" if failure == "refusal" else "timeout"
        )
        if failure == "refusal":
            assert (
                "Native participant reservation was refused." in red[0]["observations"]
            )
        assert blue[0]["status"] == "succeeded"
        states = list(snapshot.participant_autonomous_execution_states.values())
        red_state = next(
            s for s in states if s["participant_address"] == "participant.behavior.red"
        )
        blue_state = next(
            s for s in states if s["participant_address"] == "participant.behavior.blue"
        )
        assert red_state["lifecycle_state"] == (
            "failed" if policy == "stop" else "running"
        )
        assert blue_state["lifecycle_state"] == "running"
        assert red_state["next_tick"] == blue_state["next_tick"] == 1
        assert red_state["attempted_actions"] == blue_state["attempted_actions"] == 1

        bundle = report_trial_outcomes(runtime, experiment_id, metadata={})
        (run,) = bundle.runs
        attempt = run.execution_accounting.attempts[-1]
        assert run.run_status == ("indeterminate" if policy == "stop" else "completed")
        assert run.outcome_status == "not-evaluated"
        assert run.record_state == "partial"
        assert attempt.execution_status == (
            "unknown" if policy == "stop" else "succeeded"
        )
        assert attempt.cleanup_status == (
            "unobserved" if policy == "stop" else "succeeded"
        )
        assert run.ended_at is None if policy == "stop" else run.ended_at is not None
        assert run.run_id == request.run_id
        assert run.execution_accounting.plan_entry_id == request.plan_entry_id
        assert request.run_id not in bundle.eligible_run_ids

        if policy == "stop":
            before = set(operations)
            with pytest.raises(TrialPending):
                handler.execute_trial(request)
            assert set(unit.run._store.load_records()) == before
            assert action_results(unit.run.snapshot) == actions


def test_continue_policy_still_waits_when_owner_has_no_cessation_evidence(tmp_path):
    with serving(tmp_path, native_policy="continue") as (
        handler,
        request,
        services,
        runtime,
        experiment_id,
    ):
        observed = []

        def no_terminal_observation(request, snapshot):
            observed.append(snapshot)
            return TrialExecutionObservation(state="running", ceased=False, evidence=())

        services.observe = no_terminal_observation
        unit = handler.runtime_unit.unit
        handler = replace(handler, runtime_unit=unit)
        with pytest.raises(TrialPending):
            handler.execute_trial(request)
        assert observed
        assert services.events == ["configure"]
        assert (tmp_path / TRIAL_FENCE).exists()
        (run,) = report_trial_outcomes(runtime, experiment_id, metadata={}).runs
        assert run.run_status == "indeterminate"
        assert run.outcome_status == "not-evaluated"
        assert run.ended_at is None
        assert run.execution_accounting.attempts[-1].cleanup_status == "unobserved"


def test_successful_actions_do_not_advance_a_stepped_clock_or_evaluate_a_trial(
    tmp_path, monkeypatch
):
    from tests import trial_reporting_fixture

    original = trial_reporting_fixture.native_failure_bindings

    def successful_bindings():
        return tuple(
            replace(item, executor=lambda *args: "observed") for item in original()
        )

    monkeypatch.setattr(
        trial_reporting_fixture, "native_failure_bindings", successful_bindings
    )
    with serving(tmp_path, native_policy="continue") as (
        handler,
        request,
        _,
        runtime,
        experiment_id,
    ):
        result = replace(handler, runtime_unit=handler.runtime_unit.unit).execute_trial(
            request
        )
        actions = action_results(result.execution_snapshot)
        assert len(actions) == 2
        assert all(action["status"] == "succeeded" for action in actions)
        states = (
            result.execution_snapshot.participant_autonomous_execution_states.values()
        )
        assert all(
            state["next_tick"] == 1 and state["attempted_actions"] == 1
            for state in states
        )
        (run,) = report_trial_outcomes(runtime, experiment_id, metadata={}).runs
        assert run.run_status == "completed"
        assert run.outcome_status == "not-evaluated"


def test_second_native_action_requires_shared_clock_progression():
    from aptl.backends.raes_runtime import AptlRuntimeManager
    from tests.test_lilrae_concurrent_participants import bindings, scenario, target_for

    calls = []

    def executor(action, cancellation):
        calls.append(action)
        return "observed"

    installed = tuple(
        replace(
            item,
            execution_binding=replace(item.execution_binding, max_action_attempts=2),
        )
        for item in bindings({"red": executor, "blue": executor})
    )
    target, _ = target_for(installed)
    with AptlRuntimeManager(target) as manager:
        applied = manager.apply(manager.plan(scenario(attempts=2)))
        assert applied.success, applied.diagnostics
        assert len(calls) == 2
        assert all(
            s["next_tick"] == 1
            for s in manager.snapshot.participant_autonomous_execution_states.values()
        )
        advanced = manager.advance_time("time.clock.trial", ticks=1)
        assert advanced.success
        assert len(calls) == 4
        assert all(
            s["lifecycle_state"] == "completed"
            for s in manager.snapshot.participant_autonomous_execution_states.values()
        )


def test_native_failure_without_effect_proof_remains_indeterminate():
    from raes_backend_stubs.stubs import StubProvisioner, create_stub_target
    from raes_contracts.planning import ProvisioningPlan
    from raes_contracts.runtime_state import ApplyResult
    from raes_runtime import RuntimeControlPlane

    class FailedNativeCall(StubProvisioner):
        def apply(self, plan, snapshot):
            # A returned failure supplies no independent effect/cessation proof.
            return ApplyResult(False, snapshot)

    target = replace(create_stub_target(), provisioner=FailedNativeCall())
    with RuntimeControlPlane(target) as runtime:
        receipt = runtime.submit_provisioning(ProvisioningPlan())
        assert receipt.accepted
        assert (
            runtime.get_operation(receipt.operation_id).state
            is OperationState.INDETERMINATE
        )
        record = runtime._store.load_records()[receipt.operation_id]
        assert record.invocation.consumed and record.invocation.reserved
        from raes_contracts.errors import ConflictError

        with pytest.raises(
            ConflictError, match="indeterminate operation requires resolution"
        ):
            runtime.submit_provisioning(ProvisioningPlan())
