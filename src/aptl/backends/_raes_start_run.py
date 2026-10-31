"""Run target and materialization archive helpers for RAES scenario start."""

from __future__ import annotations

from pathlib import Path

from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.models import ExecutionPlan

from aptl.backends.raes_diagnostics import render_raes_diagnostics
from aptl.backends.raes_planning_compat import AptlRuntimeManager
from aptl.backends.raes_start_model import AcesRunTarget, AdmittedScenarioStart
from aptl.core.config import AptlConfig
from aptl.core.lab_types import LabResult
from aptl.core.runstore import LocalRunStore, RunStorageBackend


def admitted_run_target(
    admitted: AdmittedScenarioStart,
    run_target: AcesRunTarget | None,
    project_dir: Path,
    config: AptlConfig,
) -> AcesRunTarget | None:
    """Check the trial run identity and select the run target for the plan."""

    trial = admitted.bundle.trial
    if trial is not None and (
        run_target is None or run_target.run_id != trial.provenance.run_id
    ):
        raise ValueError("family-run-identity-mismatch")
    source = admitted.execution_plan.provisioning.materialization_source
    if source is None or run_target is not None:
        return run_target
    storage_path = Path(config.run_storage.local_path)
    if not storage_path.is_absolute():
        storage_path = project_dir / storage_path
    return AcesRunTarget(LocalRunStore(storage_path), source.run_id)


def materialization_reporting_options(
    execution_plan: ExecutionPlan,
    *,
    run_store: RunStorageBackend | None,
    run_id: str | None,
) -> dict[str, object]:
    """Return runtime options that archive materialization for the admitted run."""

    from aptl.backends.lilrae_materialization_archive import (
        LilraeMaterializationArchive,
    )

    source = execution_plan.provisioning.materialization_source
    if source is None:
        return {}
    if run_id != source.run_id or run_store is None:
        raise ValueError("The admitted plan and archive must identify the same run")
    if run_store.is_sealed(run_id):
        raise ValueError("The admitted run is sealed")
    return {
        "run_scope": f"run:{run_id}",
        "materialization_archive": LilraeMaterializationArchive(run_store, run_id),
    }


def refresh_materialized_inventory(
    manager: AptlRuntimeManager, execution_plan: ExecutionPlan
) -> tuple[LabResult | None, RuntimeSnapshot]:
    """Refresh the runtime inventory after apply and report a failed refresh."""

    refreshed = manager.refresh_inventory(execution_plan)
    failure = (
        None
        if refreshed.success
        else LabResult(
            success=False,
            error=render_raes_diagnostics(list(refreshed.diagnostics)),
        )
    )
    return failure, refreshed.snapshot
