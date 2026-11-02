"""Execute independent participants through the real RAES scheduler."""

from aptl.workbench.lilrae_opencode import OpenCodeOptions

import threading
from dataclasses import replace
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor

import pytest
from raes_contracts.immutable_history import HistoryMap

from raes_backend_protocols.capabilities import ParticipantExecutionBinding
from raes_backend_protocols.manifest import backend_manifest_v2_model
from raes_backend_stubs.stubs import create_stub_target
from raes_processor.compiler import compile_runtime_model
from raes_runtime.registry import ReferenceTimeRuntime
from aptl.backends.raes_planning_compat import AptlRuntimeManager as RuntimeManager

from aptl.backends.raes_manifest import create_aptl_manifest
from aptl.backends.raes_participant_runtime import AptlParticipantRuntime
from tests.lilrae_concurrent_fixture import apparatus, scenario


def bindings(executors):
    from aptl.backends.lilrae_participant_execution import LilraeParticipantBinding

    result = []
    for role, executor in executors.items():
        manifest, selection = apparatus(role)
        result.append(
            LilraeParticipantBinding(
                implementation_manifest=manifest,
                implementation_selection=selection,
                observation_boundary_address="participant.observation-boundary.red",
                execution_binding=ParticipantExecutionBinding(
                    binding_id=f"lilrae-{role}",
                    action_contract_address="participant.action-contract.red",
                    target_addresses=("provision.node.target.service.http",),
                    participant_implementation_ref=selection.manifest_ref,
                    constraint_refs=("time.constraint.turn",),
                    evidence_refs=(f"evidence:{role}:native",),
                    max_action_attempts=1,
                    max_in_flight=2,
                    timeout_seconds=30,
                    max_retries=0,
                ),
                executor=executor,
            )
        )
    return tuple(result)


def manager_for(installed):
    target, runtime = target_for(installed)
    return RuntimeManager(target), runtime


def target_for(installed):
    runtime = AptlParticipantRuntime(
        deployment_backend=Mock(), autonomous_bindings=installed
    )
    manifest = create_aptl_manifest(autonomous_bindings=installed)
    backend_manifest_v2_model(manifest)
    target = create_stub_target()
    manifest = replace(
        target.manifest,
        supported_contract_versions=(
            target.manifest.supported_contract_versions
            | manifest.supported_contract_versions
        ) - {
            "backend-runtime-descendants-v1",
            "backend-materialization-attestation-v1",
        },
        capabilities=replace(
            target.manifest.capabilities,
            participant_runtime=manifest.participant_runtime,
            time=manifest.time,
        ),
    )
    target = replace(
        target,
        manifest=manifest,
        participant_runtime=runtime,
        time_runtime=ReferenceTimeRuntime(),
    )
    return target, runtime


def test_real_scheduler_overlaps_red_blue_and_keeps_both_histories():
    rendezvous = threading.Barrier(2, timeout=15)
    blue_finished = threading.Event()
    completed = []

    def red(action_id, cancellation):
        rendezvous.wait()
        assert blue_finished.wait(15)
        completed.append("red")
        return "red observation"

    def blue(action_id, cancellation):
        rendezvous.wait()
        completed.append("blue")
        blue_finished.set()
        return "blue observation"

    installed = bindings({"red": red, "blue": blue})
    manager, runtime = manager_for(installed)
    authored = scenario()
    compile_runtime_model(authored)
    with manager:
        result = manager.apply(manager.plan(authored))
        assert result.success, result.diagnostics
        assert completed == ["blue", "red"]
        for role in ("red", "blue"):
            history = manager.snapshot.participant_behavior_history[
                f"participant.behavior.{role}"
            ]
            assert any(event["event_type"] == "action_attempted" for event in history)
            assert any(role + " observation" in str(event) for event in history)


@pytest.mark.parametrize("cancel_all", [False, True])
def test_cancellation_drains_owned_work_and_preserves_peer(cancel_all):
    started = threading.Barrier(3, timeout=15)

    def red(action, cancellation):
        started.wait()
        assert cancellation.wait(15)
        return "red stopped"

    def blue(action, cancellation):
        started.wait()
        if cancel_all:
            assert cancellation.wait(15)
        return "blue finished"

    manager, runtime = manager_for(bindings({"red": red, "blue": blue}))
    with manager, ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(manager.apply, manager.plan(scenario()))
        started.wait()
        runtime.autonomous_execution.cancel(
            None if cancel_all else "participant.behavior.red"
        )
        assert runtime.autonomous_execution.drain(30)
        result = future.result(timeout=30)
        assert result.success, result.diagnostics
        history = manager.snapshot.participant_behavior_history
        assert "cancelled" in str(list(history["participant.behavior.red"]))
        if not cancel_all:
            assert "blue finished" in str(list(history["participant.behavior.blue"]))


def test_unsupported_binding_rejects_batch_without_native_work():
    native = Mock(
        spec=lambda action, cancellation: None, return_value="must not execute"
    )
    installed = bindings({"red": native, "blue": native})
    invalid = replace(
        installed[1],
        execution_binding=replace(
            installed[1].execution_binding,
            target_addresses=("provision.node.another.service.http",),
        ),
    )
    manager, _ = manager_for((installed[0], invalid))
    with manager:
        plan = manager.plan(scenario())
        assert any(
            d.code == "lilrae.participant-binding-refused" for d in plan.diagnostics
        )
        result = manager.apply(plan)
        assert not result.success
    native.assert_not_called()


@pytest.mark.parametrize("failure", ["timeout", "unknown"])
def test_failed_participant_preserves_dispatched_peer_and_is_not_retried(failure):
    from aptl.workbench.process import (
        BoundedProcessError,
        ProcessCleanup,
        REASON_TIMEOUT,
    )

    started = threading.Barrier(2, timeout=15)
    calls = []

    def red(action, cancellation):
        started.wait()
        calls.append("red")
        if failure == "timeout":
            raise BoundedProcessError(
                REASON_TIMEOUT,
                cleanup=ProcessCleanup(1, 0),
                stdout_bytes=0,
                stderr_bytes=0,
            )
        raise RuntimeError("private provider error must not escape")

    def blue(action, cancellation):
        started.wait()
        calls.append("blue")
        return "blue retained"

    manager, _ = manager_for(bindings({"red": red, "blue": blue}))
    with manager:
        result = manager.apply(manager.plan(scenario()))
        history = manager.snapshot.participant_behavior_history
        assert "blue retained" in str(list(history["participant.behavior.blue"]))
        assert sorted(calls) == ["blue", "red"]
        if failure == "timeout":
            assert "timeout" in str(list(history["participant.behavior.red"]))
        else:
            assert not result.success
            assert "private provider error" not in repr(result)


def test_native_workers_receive_isolated_predecessors():
    rendezvous = threading.Barrier(2, timeout=15)
    manager, runtime = manager_for(
        bindings({"red": lambda *args: "red", "blue": lambda *args: "blue"})
    )
    native = runtime._model_action
    observed = []

    def inspect_predecessor(request, snapshot, *, episode_id):
        observed.append(snapshot)
        rendezvous.wait()
        assert observed[0] is not observed[1]
        # RAES 9 histories are immutable, so a shared history cannot carry a
        # peer's write into this worker's predecessor.
        assert isinstance(observed[0].participant_behavior_history, HistoryMap)
        assert isinstance(observed[1].participant_behavior_history, HistoryMap)
        return native(request, snapshot, episode_id=episode_id)

    runtime._model_action = inspect_predecessor
    with manager:
        result = manager.apply(manager.plan(scenario()))
        assert result.success, result.diagnostics


@pytest.mark.parametrize("invalid", ["duplicate", "capacity", "stale"])
def test_invalid_batch_or_generation_never_reaches_native_executor(invalid):
    native = Mock(spec=lambda *args: None, return_value="unexpected")
    manager, runtime = manager_for(bindings({"red": native, "blue": native}))
    admit = runtime.admit_actions_concurrently

    def changed_batch(requests, snapshot, max_workers):
        if invalid == "duplicate":
            requests = (requests[0], requests[0])
        elif invalid == "capacity":
            max_workers = 9
        else:
            requests = tuple(
                replace(request, execution_generation=request.execution_generation + 1)
                for request in requests
            )
        return admit(requests, snapshot, max_workers)

    runtime.admit_actions_concurrently = changed_batch
    with manager:
        result = manager.apply(manager.plan(scenario()))
        assert not result.success
    native.assert_not_called()


@pytest.mark.parametrize("binary", ["/bin/false", "/bin/true"])
def test_nonzero_harness_exit_preserves_peer_and_continue_policy(tmp_path, binary):
    from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor
    from pathlib import Path

    rendezvous = threading.Barrier(2, timeout=15)
    harness = LilraeOpenCodeExecutor(
        options=OpenCodeOptions(
            executable=Path(binary), work_root=tmp_path, environment={}
        ),
        model="provider/model",
        prompt="task",
        timeout_seconds=15,
    )
    calls = []

    def red(action, cancellation):
        rendezvous.wait()
        calls.append("red")
        return harness(action, cancellation)

    def blue(action, cancellation):
        rendezvous.wait()
        calls.append("blue")
        return "peer retained"

    installed = tuple(
        replace(
            item,
            execution_binding=replace(item.execution_binding, max_action_attempts=2),
        )
        for item in bindings({"red": red, "blue": blue})
    )
    manager, _ = manager_for(installed)
    with manager:
        result = manager.apply(manager.plan(scenario(attempts=2)))
        assert result.success, result.diagnostics
        advanced = manager.advance_time("time.clock.trial", ticks=1)
        assert advanced.success, advanced.diagnostics
        history = manager.snapshot.participant_behavior_history
        assert "backend_error" in str(list(history["participant.behavior.red"]))
        assert "peer retained" in str(list(history["participant.behavior.blue"]))
    assert sorted(calls) == ["blue", "blue", "red", "red"]


def test_cancellation_before_harness_launch_has_a_terminal_result(tmp_path):
    from pathlib import Path
    from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor

    harness = LilraeOpenCodeExecutor(
        options=OpenCodeOptions(
            executable=Path("/bin/false"), work_root=tmp_path, environment={}
        ),
        model="provider/model",
        prompt="task",
        timeout_seconds=15,
    )

    def red(action, cancellation):
        cancellation.set()
        return harness(action, cancellation)

    manager, _ = manager_for(
        bindings({"red": red, "blue": lambda *args: "peer retained"})
    )
    with manager:
        result = manager.apply(manager.plan(scenario()))
        assert result.success, result.diagnostics
        history = manager.snapshot.participant_behavior_history
        assert "cancelled before launch" in str(list(history["participant.behavior.red"]))
        assert "peer retained" in str(list(history["participant.behavior.blue"]))
