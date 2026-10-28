"""Apply-boundary diagnostics, retry, and workflow helpers for the RAES backend.

Split out of :mod:`aptl.backends.raes` to keep that module within its size
budget. They run around ``RuntimeManager.apply``: one refuses a plan with
blocking diagnostics, one re-attaches the provisioner's own failure report to
an apply whose diagnostics the runtime boundary masked, one classifies and
releases a retryable failed attempt, and one drives any registered orchestrator
workflows. Each is a leaf — it calls no other function in ``raes.py`` — so
``raes.py`` imports them one-directionally, with no cycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes_contracts.runtime_state import RuntimeSnapshot

from aptl.backends.raes_diagnostics import render_raes_diagnostics
from aptl.backends.raes_orchestrator import AptlOrchestrator
from aptl.backends.raes_start_model import AcesStartOutcome
from aptl.core.lab_types import LabResult
from aptl.utils.logging import get_logger

if TYPE_CHECKING:
    from pathlib import Path

    from raes_contracts.diagnostics import Diagnostic
    from raes_processor.models import ExecutionPlan
    from raes_runtime.registry import RuntimeTarget

    from aptl.core.runstore import RunStorageBackend

log = get_logger("raes-backend")

_RETRYABLE_APPLY_DIAGNOSTIC_CODES = frozenset({"aptl.provisioner.backend-start-failed"})


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


def _is_retryable_apply_failure(diagnostics: list[Diagnostic]) -> bool:
    """Only the deployment-backend start diagnostic is retryable."""

    return any(
        diagnostic.code in _RETRYABLE_APPLY_DIAGNOSTIC_CODES
        for diagnostic in diagnostics
    )


def _release_failed_attempt(outcome: AcesStartOutcome) -> AcesStartOutcome | None:
    """Close the failed attempt's manager so the retry can own the target.

    RAES lets one live manager own a target's components, and the retry builds
    a new manager from the admitted base snapshot (issue #1424). A manager that
    does not close keeps that ownership, so the start fails with the first
    failure instead of a retry that cannot own the target.
    """

    manager = outcome.runtime_manager
    if manager is None:
        return None
    try:
        manager.close()
    except (RuntimeError, TimeoutError) as exc:
        log.warning("Backend retry stopped: the failed runtime manager did not close")
        outcome.lab_result = LabResult(
            success=False,
            error=(
                f"{outcome.lab_result.error}\nAutomatic retry stopped: the "
                f"failed attempt's runtime manager did not close ({exc})."
            ),
        )
        outcome.retryable = False
        return outcome
    return None


def _with_backend_failure_diagnostics(
    target: RuntimeTarget,
    diagnostics: list[Diagnostic],
) -> list[Diagnostic]:
    """Re-attach the provisioner's own failure report to a failed apply.

    ``raes_runtime``'s backend-call boundary replaces a failed backend apply's
    diagnostics with its snapshot-contract / SEM-218 gate output — the gate
    evaluates the never-realized snapshot, so every exact declaration reads as
    unrealized. That hides the backend's actionable failure (for example a
    Docker subnet conflict with its remediation steps) and severs the
    retryable-code signal the SOC retry keys on. The backend's own report is
    authoritative for what failed, so it renders first.
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


def _drive_orchestrator_workflows(
    orchestrator: object,
    evaluation_results: dict[str, dict[str, object]],
    *,
    run_store: RunStorageBackend | None = None,
    run_id: str | None = None,
) -> LabResult | None:
    """Drive registered workflows and convert diagnostics to a lab failure."""

    drive_diagnostics = []
    if isinstance(orchestrator, AptlOrchestrator) and orchestrator.results():
        drive_diagnostics = orchestrator.drive_workflows(
            evaluation_results=evaluation_results,
            run_store=run_store,
            run_id=run_id,
        )
    failure = None
    if drive_diagnostics:
        failure = LabResult(
            success=False,
            error=render_raes_diagnostics(drive_diagnostics),
        )
    return failure
