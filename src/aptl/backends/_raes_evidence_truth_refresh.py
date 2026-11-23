"""Evidence truth refresh results for the APTL RAES evaluator."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from raes_contracts.contracts import ExperimentEvidenceRecordModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import (
    OperationReceipt,
    OperationState,
    RuntimeSnapshot,
)
from raes_processor.models import ExecutionPlan
from raes_runtime.control_plane import RuntimeControlPlane

from aptl.backends._raes_evaluator_engine import (
    EVALUATION_ADDRESS,
    evaluation_diagnostic,
)
from aptl.backends._raes_proposition_truth import native_evidence_truth_is_complete


@dataclass(frozen=True)
class EvidenceTruthRefresh(object):
    """Terminal result of a post-capture evaluator reconciliation."""

    status: OperationState
    snapshot: RuntimeSnapshot
    diagnostics: tuple[Diagnostic, ...] = ()


def evidence_cut_key(
    evidence_records: tuple[ExperimentEvidenceRecordModel, ...],
) -> str:
    """Name one evidence collection; RAES requires a new key for each one."""

    digest = hashlib.sha256(
        json.dumps(
            [record.model_dump(mode="json") for record in evidence_records],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return f"aptl-native-evidence-{digest}"


def evidence_refresh_result(
    control_plane: RuntimeControlPlane,
    receipt: OperationReceipt,
    execution_plan: ExecutionPlan,
    evidence_records: tuple[ExperimentEvidenceRecordModel, ...],
    proposition_interpreter: object | None,
) -> EvidenceTruthRefresh:
    """Return the exact terminal disposition of one evidence evaluation."""

    operation = (
        control_plane.get_operation(receipt.operation_id) if receipt.accepted else None
    )
    snapshot = control_plane.snapshot
    if not receipt.accepted:
        result = EvidenceTruthRefresh(
            status=OperationState.FAILED,
            snapshot=snapshot,
            diagnostics=tuple(receipt.diagnostics),
        )
    elif operation is None:
        result = EvidenceTruthRefresh(
            status=OperationState.FAILED,
            snapshot=snapshot,
            diagnostics=(
                evaluation_diagnostic(
                    "aptl.evaluator.native-evidence-refresh-incomplete",
                    EVALUATION_ADDRESS,
                    "RAES did not return a terminal evidence evaluation operation.",
                ),
            ),
        )
    elif (
        operation.state is OperationState.SUCCEEDED
        and not native_evidence_truth_is_complete(
            execution_plan.evaluation,
            snapshot,
            evidence_records,
            proposition_interpreter,
        )
    ):
        result = EvidenceTruthRefresh(
            status=OperationState.FAILED,
            snapshot=snapshot,
            diagnostics=(
                evaluation_diagnostic(
                    "aptl.evaluator.native-evidence-truth-incomplete",
                    EVALUATION_ADDRESS,
                    "Not every required native evidence record decided its exact authored proposition.",
                ),
            ),
        )
    else:
        result = EvidenceTruthRefresh(
            status=operation.state,
            snapshot=snapshot,
            diagnostics=tuple(operation.diagnostics),
        )
    return result
