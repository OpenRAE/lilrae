"""Compose and run the trial that a started lab's SDL declares (#1670)."""

from __future__ import annotations

import shutil
import signal
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
import os
from typing import TYPE_CHECKING

from raes_contracts.contracts import ParticipantControlContextAssetModel
from raes_env_packs import resolve_pack_artifact

from aptl.core.config import (
    AptlConfig,
    AttachedServiceAccountSource,
    find_config,
    load_config,
)
from aptl.core.lab import finalize_trial_capture
from aptl.core.mcp_policy import configured_server_ids
from aptl.core.opencode import OpenCodeInvocationEvidence
from aptl.core.runstore import LocalRunStore
from aptl.utils.redaction import redact
from aptl.utils.logging import get_logger
from aptl.core.trial_attempt import TrialAttempt
from aptl.core.trial_control import TrialControl
from aptl.core.trial_record import TrialRecord, retain_trial_capture, seal_trial_record
from aptl.backends.raes_start_model import StartedTrialRuntime
from aptl.backends.raes_evidence_acquisition import NativeEvidenceRequest
from aptl.core.evidence.trial_sources import (
    SESSION_REGISTRATION,
    AUDIT_REGISTRATION,
    participant_session_source,
    host_audit_source,
)
from aptl.core.trial_sdl import (
    admitted_participants,
)
from aptl.workbench.trial_launch import (
    TrialLaunchSettings,
    invocation_fields,
    trial_executors,
)
from aptl.workbench.trial_run import DeclaredTrial, run_declared_trial

if TYPE_CHECKING:

    pass

log = get_logger("lab_trial")

__all__ = ["refuse_existing_trial_run", "run_lab_trial", "trial_summary"]

_WORK_DIR = Path(".aptl/trial-work")


def refuse_existing_trial_run(project_dir: Path, attempt: TrialAttempt) -> None:
    """Refuse a run ID that already names a run, before any lab change."""
    config_path = find_config(project_dir)
    config = load_config(config_path) if config_path is not None else AptlConfig()
    base = _run_store_base(config_path.parent if config_path else project_dir, config)
    if (base / attempt.run_id).exists():
        raise ValueError(
            f"run {attempt.run_id} already exists; a trial needs a new run ID"
        )


def run_lab_trial(
    project_dir: Path,
    attempt: TrialAttempt,
    *,
    scenario_path: Path | None,
    scenario_sha256: str,
    progress: Callable[[str], None],
    started: StartedTrialRuntime | None = None,
) -> TrialRecord:
    """Run the declared participants on the started lab and seal the run.

    The trial refuses an SDL whose digest differs from the one startup admitted.
    """
    if not isinstance(started, StartedTrialRuntime):
        raise ValueError(
            "a trial requires the runtime that admitted and started its lab"
        )
    root = project_dir.resolve()
    control = TrialControl(root)
    try:
        config = started.admitted.target.provisioner.config
        control.begin(attempt)
        record, gaps = _run_and_drain(
            root, config, attempt, scenario_sha256, progress, started
        )
        cleanup = {**record.cleanup, "transcripts": finalize_trial_capture(root)}
        if cleanup["transcripts"] == "failed":
            gaps = (*gaps, "required shell transcript finalization failed")
        record = record.model_copy(update={"cleanup": cleanup})
        seal_trial_record(
            started.run_store,
            record,
            gaps=gaps,
        )
        progress(
            f"Trial ended by {record.terminal_cause}; run {record.run_id} is sealed."
        )
        return record
    finally:
        try:
            started.runtime.close()
        finally:
            shutil.rmtree(root / _WORK_DIR, ignore_errors=True)
            control.release(attempt)


def trial_summary(record: TrialRecord) -> dict[str, object]:
    """Return the JSON fields that ``lab start --json`` reports for a trial."""
    return {
        "run_id": record.run_id,
        "attempt_id": record.attempt_id,
        "terminal_cause": record.terminal_cause,
        "participants": [
            {"address": item.address, "status": item.status}
            for item in record.participants
        ],
        "cleanup": dict(record.cleanup),
    }


def _run_and_drain(
    root: Path,
    config: AptlConfig,
    attempt: TrialAttempt,
    scenario_sha256: str,
    progress: Callable[[str], None],
    started: StartedTrialRuntime,
) -> tuple[TrialRecord, tuple[str, ...]]:
    """Use the exact startup owner for native scheduling, acquisition and evaluation."""
    admitted = started.admitted
    trial = admitted.bundle.trial
    plan = admitted.trial_capture_plan
    if trial is None or trial.snapshot_digest != scenario_sha256 or plan is None:
        raise ValueError("the admitted trial or its measurement plan is unavailable")
    scenario = trial.scenario
    participants = admitted_participants(
        scenario, trial.participant_configuration_results
    )
    native = admitted.target.participant_runtime.autonomous_execution
    policies = [
        spec.autonomous_execution
        for spec in admitted.execution_plan.model.behavior_specifications.values()
        if spec.autonomous_execution is not None
    ]
    if len(policies) != 1:
        raise ValueError("this trial requires one native participant release policy")
    policy = policies[0]
    bindings = {
        "agents."
        + binding.implementation_selection.participant_address.removeprefix(
            "participant.behavior."
        ): binding
        for binding in native.bindings
    }
    durations = {
        binding.execution_binding.timeout_seconds for binding in native.bindings
    }
    if len(durations) != 1:
        raise ValueError("the participants must share the admitted episode bound")
    store = started.run_store
    if not isinstance(store, LocalRunStore):
        raise ValueError("the installed trial requires its local evidence store")
    evidence, sessions, records = {}, {}, []

    def sink(address: str, item: OpenCodeInvocationEvidence) -> None:
        evidence[address] = invocation_fields(item)

    def transcript_sink(address: str, session: Mapping[str, object]) -> None:
        sessions[address] = session

    def read_asset(asset: ParticipantControlContextAssetModel) -> bytes:
        return resolve_pack_artifact(
            str(admitted.bundle.root), asset.content.artifact_id
        ).data

    from aptl.core.env import load_dotenv

    environment = load_dotenv(root / ".env")
    request = NativeEvidenceRequest(
        plan=plan,
        backend=started.backend,
        realization=admitted.realization,
        project_dir=root,
        environment=environment,
        run_store=store,
        run_id=attempt.run_id,
        capture_selection=admitted.capture_selection,
    )
    progress(f"Preparing {len(participants)} native trial participants.")
    with (
        _termination_stops() as terminated,
        trial_executors(
            scenario,
            participants,
            attempt=attempt,
            bindings=bindings,
            settings=_launch_settings(root, config, attempt),
            read_asset=read_asset,
            evidence_sink=sink,
            transcript_sink=transcript_sink,
        ) as executors,
    ):
        control = TrialControl(root)

        def execute():
            records.append(
                run_declared_trial(
                    DeclaredTrial(
                        attempt, scenario_sha256, participants, durations.pop()
                    ),
                    runtime=started.runtime,
                    native=native,
                    policy=policy,
                    invocations=executors,
                    evidence=evidence,
                    stop_requested=lambda: (
                        terminated.is_set() or control.stop_requested()
                    ),
                    store=store,
                    clock=lambda: datetime.now(UTC),
                )
            )
            observer = getattr(
                admitted.capture_selection.contribution.runtime_adapter,
                "observe_trial_end",
                None,
            )
            if callable(observer):
                observer(records[0].started_at, records[0].ended_at)

        capture = started.runtime.collect_evidence(
            request,
            attempt_id=attempt.attempt_id,
            sources={
                SESSION_REGISTRATION: participant_session_source(
                    sessions, tuple(bindings)
                ),
                AUDIT_REGISTRATION: host_audit_source(),
            },
            trial_body=execute,
        )
    if len(records) != 1:
        raise RuntimeError(
            "required capture refused the trial before participant release"
        )
    record = retain_trial_capture(store, records[0], plan, capture)
    from aptl.backends.raes_evaluator import refresh_evidence_truth
    from aptl.backends.raes_repro import runtime_snapshot_record_payload

    refresh_evidence_truth(
        target=admitted.target,
        execution_plan=admitted.execution_plan,
        snapshot=started.runtime.snapshot,
        evidence_records=(*started.initial_evidence, *capture.records),
        runtime_manager=started.runtime,
    )
    snapshot = started.runtime.snapshot
    objectives = {
        address: value
        for address, value in snapshot.evaluation_results.items()
        if address.startswith("evaluation.objective.")
    }
    store.create_run_json_once(
        attempt.run_id,
        "trial/evaluation.json",
        {
            "objectives": objectives,
            "proposition_truth_results": dict(snapshot.proposition_truth_results),
        },
    )
    store.create_run_json_once(
        attempt.run_id,
        "trial/evaluated-runtime.json",
        {
            "redaction_policy": "redact_secrets",
            "snapshot": redact(runtime_snapshot_record_payload(snapshot)),
        },
    )
    values = [item.get("passed") for item in objectives.values()]
    status = (
        "inconclusive"
        if not values or any(value is None for value in values)
        else "succeeded"
        if all(values)
        else "partial"
        if any(values)
        else "failed"
    )
    cleanup = {"provider_access": "removed"}
    if isinstance(
        config.experiment.participant_credential_sources.vertex,
        AttachedServiceAccountSource,
    ):
        cleanup["vertex_access"] = "attached-service-account"
    return record.model_copy(update={"cleanup": cleanup, "outcome_status": status}), ()


@contextmanager
def _termination_stops() -> Iterator[object]:
    """Treat SIGTERM to this process as a stop request while participants run."""
    from threading import Event

    terminated = Event()
    previous = signal.signal(signal.SIGTERM, lambda signum, frame: terminated.set())
    try:
        yield terminated
    finally:
        signal.signal(signal.SIGTERM, previous)


def _run_store_base(config_root: Path, config: AptlConfig) -> Path:
    """Resolve the configured run store against the configuration directory."""
    base = Path(config.run_storage.local_path)
    return base if base.is_absolute() else config_root / base


def _launch_settings(
    root: Path, config: AptlConfig, attempt: TrialAttempt
) -> TrialLaunchSettings:
    """Collect the operator settings that every participant launch uses."""
    executable = config.experiment.opencode_executable
    if executable is None:
        raise ValueError(
            "aptl.json experiment.opencode_executable must name the OpenCode build"
        )
    work_root = root / _WORK_DIR
    work_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(work_root, 0o700)
    mcp_config = root / ".mcp.json"
    return TrialLaunchSettings(
        executable=Path(executable),
        work_root=work_root,
        experiment=config.experiment,
        source_environment=dict(os.environ),
        mcp_config=mcp_config if mcp_config.is_file() else None,
        server_ids=configured_server_ids(root, attempt.run_id),
    )
