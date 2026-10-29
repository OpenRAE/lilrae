"""RAES workload bridge to the existing experiment terminal-attempt owner."""

from __future__ import annotations

from collections.abc import Callable

from raes_processor.models import ExecutionPlan
from raes_runtime.registry import RuntimeTarget
from raes_contracts.runtime_state import RuntimeSnapshot

from aptl.backends.raes_participant_runtime import AptlParticipantRuntime
from aptl.backends.raes_planning_compat import AptlRuntimeManager
from aptl.core.execution.assembly import (
    TrialExecutionContext,
    TrialOutcome,
    TrialTerminalSignal,
)
from aptl.core.archival.status import TerminalCause, map_terminal_cause


def run_participant_workload(
    context: TrialExecutionContext,
    *,
    target: RuntimeTarget,
    execution_plan: ExecutionPlan,
    evaluate: Callable[[RuntimeSnapshot], TrialOutcome] | None = None,
) -> TrialOutcome:
    """Execute one admitted trial, then drain before returning to the seal owner.

    The caller builds a fresh target and exact executors from this trial's
    configuration results. Cancellation uses that target's native execution
    handle. This function neither provisions another scheduler nor seals data.
    Scenario evaluation remains in the supplied RAES plan.
    """
    runtime = target.participant_runtime
    if not isinstance(runtime, AptlParticipantRuntime):
        raise ValueError("participant workload requires the installed LilRAE runtime")
    native = runtime.autonomous_execution
    _validate_trial_configuration(context, runtime)
    with AptlRuntimeManager(
        target, initial_snapshot=execution_plan.base_snapshot
    ) as manager:
        try:
            result = manager.apply(execution_plan)
            signal = _terminal_signal(
                result.success, native.trial_cancelled, manager.snapshot
            )
            snapshot = manager.snapshot
        finally:
            # The supported simulated, stepped policy dispatches synchronously;
            # RAES joins the entire batch before apply returns or raises.
            native.cancel()
            if not native.drain(30):
                raise RuntimeError("participant workload cleanup did not complete")
    if signal is not TrialTerminalSignal.COMPLETED:
        return TrialOutcome(signal=signal)
    return _evaluation_outcome(evaluate, snapshot)


def _evaluation_outcome(
    evaluate: Callable[[RuntimeSnapshot], TrialOutcome] | None,
    snapshot: RuntimeSnapshot,
) -> TrialOutcome:
    """Preserve the task evaluator's verdict; never infer it from process success."""
    try:
        outcome = evaluate(snapshot) if evaluate is not None else None
        if not isinstance(outcome, TrialOutcome):
            raise ValueError("no evaluator verdict")
        if outcome.signal is TrialTerminalSignal.COMPLETED:
            map_terminal_cause(
                TerminalCause.COMPLETED, evaluator_outcome=outcome.evaluator_outcome
            )
        return outcome
    except Exception:
        return TrialOutcome(signal=TrialTerminalSignal.EVALUATOR_FAILURE)


def _validate_trial_configuration(
    context: TrialExecutionContext, runtime: AptlParticipantRuntime
) -> None:
    configured = {}
    for binding in runtime.autonomous_execution.bindings:
        result = getattr(binding.executor, "configuration_result", None)
        if result is not None:
            address = binding.implementation_selection.participant_address
            if address in configured and configured[address] != result:
                raise ValueError("participant has conflicting installed configurations")
            configured[address] = result
    planned = context.planned_trial.participant_configurations
    if len({item.participant_address for item in planned}) != len(planned):
        raise ValueError("trial has duplicate participant configurations")
    if configured != {item.participant_address: item for item in planned}:
        raise ValueError(
            "installed participant configuration differs from the planned trial"
        )


def _terminal_signal(
    success: bool, cancelled: bool, snapshot: RuntimeSnapshot
) -> TrialTerminalSignal:
    if not success:
        return TrialTerminalSignal.INTERRUPTED
    if cancelled:
        return TrialTerminalSignal.CANCELLED
    if any(
        event.get("action_result", {}).get("status") == "failed"
        for history in snapshot.participant_behavior_history.values()
        for event in history
    ):
        return TrialTerminalSignal.SCENARIO_FAILURE
    return TrialTerminalSignal.COMPLETED
