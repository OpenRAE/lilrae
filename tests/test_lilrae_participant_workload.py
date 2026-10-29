"""The experiment owner receives a terminal signal only after native cleanup."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

from aptl.core.execution.assembly import TrialExecutionContext, TrialTerminalSignal
from aptl.core.evidence.protocol import RunScope
from tests.test_execution_executor import _admitted, _completed_workload
from tests.test_lilrae_concurrent_participants import bindings, target_for, scenario
from raes_runtime.manager import RuntimeManager


def test_trial_cancellation_returns_after_both_workers_cleanup():
    from aptl.backends.lilrae_participant_workload import run_participant_workload

    started = Barrier(3, timeout=15)
    cleaned = {role: Event() for role in ("red", "blue")}

    def executor(role):
        def run(action, cancellation):
            started.wait()
            assert cancellation.wait(15)
            cleaned[role].set()
            return "stopped"

        return run

    target, runtime = target_for(bindings({role: executor(role) for role in cleaned}))
    with RuntimeManager(target) as manager:
        plan = manager.plan(scenario())
    trial = _admitted().plan.trials[0]
    context = TrialExecutionContext(
        "attempt", trial, RunScope("attempt", trial.planned_trial_id, "attempt")
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            run_participant_workload, context, target=target, execution_plan=plan
        )
        started.wait()
        runtime.autonomous_execution.cancel()
        outcome = future.result(timeout=30)
    assert all(event.is_set() for event in cleaned.values())
    assert outcome.signal == TrialTerminalSignal.CANCELLED


def test_trial_configuration_mismatch_fails_before_native_dispatch():
    from dataclasses import replace
    import pytest
    from unittest.mock import Mock
    from aptl.backends.lilrae_participant_workload import run_participant_workload
    from tests.test_lilrae_participant_configuration import configuration

    native = Mock(spec=lambda *args: None)
    target, _ = target_for(bindings({"red": native, "blue": native}))
    with RuntimeManager(target) as manager:
        plan = manager.plan(scenario())
    _, result = configuration()
    trial = replace(_admitted().plan.trials[0], participant_configurations=(result,))
    context = TrialExecutionContext(
        "attempt", trial, RunScope("attempt", trial.planned_trial_id, "attempt")
    )
    with pytest.raises(ValueError, match="configuration"):
        run_participant_workload(context, target=target, execution_plan=plan)
    native.assert_not_called()


def test_consecutive_trials_deliver_independent_prompt_variants(tmp_path):
    from dataclasses import replace
    from pathlib import Path
    from aptl.backends.lilrae_participant_configuration import (
        configured_opencode_executor,
    )
    from aptl.backends.lilrae_participant_workload import run_participant_workload
    from tests.test_lilrae_opencode import RecordingRunner
    from tests.test_lilrae_participant_configuration import configuration

    contexts = []
    for red_prompt, blue_prompt in (
        ("red task", "blue task"),
        ("changed red", "blue task"),
        ("changed red", "changed blue"),
    ):
        installed = []
        configured = []
        runners = []
        rendezvous = Barrier(2, timeout=15)

        class ConcurrentRunner(RecordingRunner):
            def run(self, argv, **options):
                rendezvous.wait()
                return super().run(argv, **options)

        for binding, prompt in zip(
            bindings({"red": lambda *args: "", "blue": lambda *args: ""}),
            (red_prompt, blue_prompt),
        ):
            role = binding.implementation_selection.participant_address.rsplit(".", 1)[
                1
            ]
            manifest, result = configuration(
                prompt=prompt,
                role=role,
                manifest_ref=binding.implementation_selection.manifest_ref,
            )
            runner = ConcurrentRunner()
            executor = configured_opencode_executor(
                configuration=result,
                manifest=manifest,
                prompt=prompt,
                prompt_ref="content.red-prompt@v1",
                supported_models=frozenset({"provider/model"}),
                executable=Path("/bin/true"),
                work_root=tmp_path,
                environment={},
                runner=runner,
            )
            selection = binding.implementation_selection.model_copy(
                update={
                    "implementation_identity": manifest.identity,
                    "manifest_digest": result.manifest_digest,
                    "configuration_ref": "participant-implementation-configurations."
                    + role,
                    "configuration_digest": result.configuration_digest,
                }
            )
            installed.append(
                replace(
                    binding,
                    implementation_manifest=manifest,
                    implementation_selection=selection,
                    executor=executor,
                    execution_binding=replace(
                        binding.execution_binding, timeout_seconds=37
                    ),
                )
            )
            configured.append(result)
            runners.append(runner)
        target, _ = target_for(tuple(installed))
        with RuntimeManager(target) as manager:
            plan = manager.plan(scenario())
        trial = replace(
            _admitted().plan.trials[0], participant_configurations=tuple(configured)
        )
        context = TrialExecutionContext(
            "attempt", trial, RunScope("attempt", trial.planned_trial_id, "attempt")
        )
        outcome = run_participant_workload(
            context,
            target=target,
            execution_plan=plan,
            evaluate=lambda snapshot: _completed_workload(None),
        )
        assert outcome.signal == TrialTerminalSignal.COMPLETED
        assert [runner.calls[0][1]["stdin"] for runner in runners] == [
            red_prompt.encode(),
            blue_prompt.encode(),
        ]
        contexts.extend(runner.calls[0][1]["cwd"] for runner in runners)
    assert len(set(contexts)) == 6
    assert all(not path.exists() for path in contexts)


def test_workload_passes_actual_evaluator_verdict_through_final_sealing(tmp_path):
    from dataclasses import replace
    from aptl.backends.lilrae_participant_workload import run_participant_workload
    from aptl.core.execution.executor import ExperimentExecutor
    from tests.test_execution_executor import _CLOCK, _store

    store = _store(tmp_path)
    target, _ = target_for(
        bindings({"red": lambda *args: "red", "blue": lambda *args: "blue"})
    )
    with RuntimeManager(target) as manager:
        plan = manager.plan(scenario())
    evaluated = replace(_completed_workload(None), evaluator_outcome="failed")
    observed = []

    def evaluate(snapshot):
        observed.append(snapshot)
        return evaluated

    executor = ExperimentExecutor(
        store=store,
        clock=_CLOCK,
        collectors={},
        workload=lambda context: run_participant_workload(
            context, target=target, execution_plan=plan, evaluate=evaluate
        ),
    )
    admitted = _admitted()
    result = executor.execute_trial(admitted, admitted.plan.trials[0])
    assert result.run.run_status == "completed"
    assert result.run.outcome_status == "failed"
    assert store.is_sealed(result.run.run_id)
    assert len(observed) == 1
    assert "blue" in str(observed[0].participant_behavior_history)


def test_missing_evaluator_verdict_seals_as_evaluator_failure(tmp_path):
    from aptl.backends.lilrae_participant_workload import run_participant_workload
    from aptl.core.execution.executor import ExperimentExecutor
    from tests.test_execution_executor import _CLOCK, _store

    store = _store(tmp_path)
    target, _ = target_for(
        bindings({"red": lambda *args: "red", "blue": lambda *args: "blue"})
    )
    with RuntimeManager(target) as manager:
        plan = manager.plan(scenario())
    executor = ExperimentExecutor(
        store=store,
        clock=_CLOCK,
        collectors={},
        workload=lambda context: run_participant_workload(
            context, target=target, execution_plan=plan
        ),
    )
    admitted = _admitted()
    result = executor.execute_trial(admitted, admitted.plan.trials[0])
    assert result.run.run_status == "failed"
    assert result.run.outcome_status == "failed"
    assert store.is_sealed(result.run.run_id)
