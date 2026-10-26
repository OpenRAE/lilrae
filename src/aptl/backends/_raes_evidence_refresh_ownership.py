"""Hand a target's runtime ownership to the native evidence refresh and back.

RAES admits one live runtime manager or control plane per target component. A
successful lab start keeps its apply manager in the start outcome, and the
native evidence refresh then builds its own control plane for the same target,
which RAES refuses ("backend already has a runtime owner"). The start's manager
is therefore closed before the refresh, as the retry closes a failed attempt's
manager (issue #1424). After a successful refresh a new manager owns the target
from the refreshed snapshot, so later steps such as participant inject delivery
keep a live owner of the current truth.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from raes_contracts.runtime_state import OperationState, RuntimeSnapshot

from aptl.backends import raes_evaluator
from aptl.backends._raes_evaluator_engine import EVALUATION_ADDRESS, evaluation_diagnostic
from aptl.backends.raes_evaluator import EvidenceTruthRefresh
from aptl.backends.raes_planning_compat import AptlRuntimeManager

if TYPE_CHECKING:
    from raes_contracts.contracts import ExperimentEvidenceRecordModel
    from raes_processor.models import ExecutionPlan
    from raes_runtime.registry import RuntimeTarget

    from aptl.backends.raes_start_model import AcesStartOutcome

OWNER_NOT_RELEASED = "aptl.evaluator.start-runtime-owner-not-released"


def release_start_runtime_owner(outcome: AcesStartOutcome | None) -> str | None:
    """Close the start's runtime manager; return why, if it did not close."""

    manager = getattr(outcome, "runtime_manager", None)
    reason = None
    if outcome is not None and manager is not None:
        try:
            manager.close()
        except (RuntimeError, TimeoutError) as exc:
            reason = f"the start's runtime manager did not close ({exc})"
        else:
            outcome.runtime_manager = None
    return reason


def refresh_evidence_truth_with_start_owner(
    outcome: AcesStartOutcome | None,
    *,
    target: RuntimeTarget,
    execution_plan: ExecutionPlan,
    snapshot: RuntimeSnapshot,
    evidence_records: Sequence[ExperimentEvidenceRecordModel],
) -> EvidenceTruthRefresh:
    """Refresh native evidence truth while the start's manager has released the target."""

    had_owner = getattr(outcome, "runtime_manager", None) is not None
    reason = release_start_runtime_owner(outcome)
    if reason is not None:
        return EvidenceTruthRefresh(
            status=OperationState.FAILED,
            snapshot=snapshot,
            diagnostics=(
                evaluation_diagnostic(
                    OWNER_NOT_RELEASED,
                    EVALUATION_ADDRESS,
                    f"Native evidence refresh could not own the target: {reason}.",
                ),
            ),
        )
    # Looked up on the module at call time, the seam lab start's tests replace.
    refresh = raes_evaluator.refresh_evidence_truth(
        target=target,
        execution_plan=execution_plan,
        snapshot=snapshot,
        evidence_records=tuple(evidence_records),
    )
    if outcome is not None and had_owner and refresh.status is OperationState.SUCCEEDED:
        outcome.runtime_manager = AptlRuntimeManager(target, initial_snapshot=refresh.snapshot)
    return refresh


__all__ = [
    "OWNER_NOT_RELEASED",
    "refresh_evidence_truth_with_start_owner",
    "release_start_runtime_owner",
]
