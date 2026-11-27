"""Apply-boundary diagnostics and workflow helpers for the RAES backend.

Split out of :mod:`aptl.backends.raes` to keep that module within its size
budget. They run around ``RuntimeManager.apply``: one refuses a plan with
blocking diagnostics, one re-attaches the provisioner's own failure report to
an apply whose diagnostics the runtime boundary masked, and one writes the
runtime's workflow records into the run archive. Each is a leaf — it calls no other function in ``raes.py`` — so
``raes.py`` imports them one-directionally, with no cycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes_contracts.runtime_state import RuntimeSnapshot

from aptl.backends.raes_diagnostics import render_raes_diagnostics
from aptl.backends.raes_start_model import AcesStartOutcome
from aptl.core.lab_types import LabResult

if TYPE_CHECKING:
    from pathlib import Path

    from raes_contracts.diagnostics import Diagnostic
    from raes_processor.models import ExecutionPlan
    from raes_runtime.registry import RuntimeTarget

    from aptl.core.runstore import RunStorageBackend


def _blocked_plan_outcome(
    execution_plan: ExecutionPlan,
    scenario_path: Path | None,
) -> AcesStartOutcome | None:
    """Fail closed on a plan whose planner reported an error."""

    blocking = [diag for diag in execution_plan.diagnostics if diag.is_error]
    if not blocking:
        return None
    return AcesStartOutcome(
        lab_result=LabResult(success=False, error=render_raes_diagnostics(blocking)),
        final_snapshot=RuntimeSnapshot(),
        realization_details={},
        selected_profiles=[],
        scenario_path=scenario_path,
    )


def _with_backend_failure_diagnostics(
    target: RuntimeTarget,
    diagnostics: list[Diagnostic],
) -> list[Diagnostic]:
    """Re-attach the provisioner's own failure report to a failed apply.

    ``raes_runtime``'s backend-call boundary replaces a failed backend apply's
    diagnostics with its snapshot-contract / SEM-218 gate output — the gate
    evaluates the never-realized snapshot, so every exact declaration reads as
    unrealized. That hides the backend's actionable failure (for example a
    Docker subnet conflict with its remediation steps). The backend's own
    report is authoritative for what failed, so it renders first.
    """
    captured = tuple(getattr(target.provisioner, "last_failure_diagnostics", ()))
    if not captured:
        return diagnostics
    seen = {
        (diagnostic.code, diagnostic.address, diagnostic.message)
        for diagnostic in diagnostics
    }
    fresh = [
        diagnostic
        for diagnostic in captured
        if (diagnostic.code, diagnostic.address, diagnostic.message) not in seen
    ]
    return [*fresh, *diagnostics]


def _archive_workflow_runs(
    snapshot: RuntimeSnapshot,
    run_store: RunStorageBackend | None,
    run_id: str | None,
) -> None:
    """Write the runtime's workflow results and history into the run archive."""

    if run_store is None or run_id is None:
        return
    for address, result in snapshot.orchestration_results.items():
        safe_address = address.replace("/", "_")
        run_store.write_json(
            run_id, f"orchestration/{safe_address}/result.json", dict(result)
        )
        history = snapshot.orchestration_history.get(address, ())
        if history:
            # ``append_jsonl`` takes the whole batch of records and redacts
            # each one (issue #993).
            run_store.append_jsonl(
                run_id,
                f"orchestration/{safe_address}/history.jsonl",
                [dict(event) for event in history],
            )
