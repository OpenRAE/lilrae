"""Compose and run the trial that a started lab's SDL declares (#1670)."""

from __future__ import annotations

import shutil
import signal
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import os

from raes import Scenario
from raes_contracts.contracts import ParticipantControlContextAssetModel
from raes_env_packs import resolve_pack_artifact
from raes_processor.models import ParticipantAutonomousExecutionRuntime

from aptl.core.config import (
    AptlConfig,
    AttachedServiceAccountSource,
    find_config,
    load_config,
)
from aptl.core.env import load_dotenv
from aptl.core.evidence.coordinator import AcquisitionResult
from aptl.core.experiment.capture_plan import CapturePlan
from aptl.core.lab import finalize_trial_capture
from aptl.core.participant_binding import LilraeParticipantBinding
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
from aptl.core.trial_sdl import DeclaredParticipant, admitted_participants
from aptl.workbench.trial_launch import (
    TrialLaunchSettings,
    TrialSinks,
    invocation_fields,
    trial_executors,
)
from aptl.workbench.trial_run import (
    DeclaredTrial,
    NativeTrialRelease,
    TrialSupervision,
    native_participant_address,
    run_declared_trial,
)

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


@dataclass(frozen=True)
class _AdmittedTrialInputs:
    """The admitted trial facts that the native release and its capture use."""

    scenario: Scenario
    scenario_sha256: str
    plan: CapturePlan
    participants: tuple[DeclaredParticipant, ...]
    release: NativeTrialRelease
    bindings: Mapping[str, LilraeParticipantBinding]
    episode_seconds: int
    store: LocalRunStore


def _run_and_drain(
    root: Path,
    config: AptlConfig,
    attempt: TrialAttempt,
    scenario_sha256: str,
    progress: Callable[[str], None],
    started: StartedTrialRuntime,
) -> tuple[TrialRecord, tuple[str, ...]]:
    """Use the exact startup owner for native scheduling, acquisition and evaluation."""
    inputs = _admitted_trial_inputs(started, scenario_sha256)
    record, capture = _release_with_capture(
        root, config, attempt, progress, started, inputs
    )
    record = retain_trial_capture(inputs.store, record, inputs.plan, capture)
    status = _evaluate_trial(started, inputs.store, attempt.run_id, capture)
    return record.model_copy(
        update={"cleanup": _cleanup_fields(config), "outcome_status": status}
    ), ()


def _admitted_trial_inputs(
    started: StartedTrialRuntime, scenario_sha256: str
) -> _AdmittedTrialInputs:
    """Check the startup admission and collect the trial facts it fixed."""
    admitted = started.admitted
    trial = admitted.bundle.trial
    plan = admitted.trial_capture_plan
    if trial is None or trial.snapshot_digest != scenario_sha256 or plan is None:
        raise ValueError("the admitted trial or its measurement plan is unavailable")
    native = admitted.target.participant_runtime.autonomous_execution
    store = started.run_store
    if not isinstance(store, LocalRunStore):
        raise ValueError("the installed trial requires its local evidence store")
    return _AdmittedTrialInputs(
        scenario=trial.scenario,
        scenario_sha256=scenario_sha256,
        plan=plan,
        participants=admitted_participants(
            trial.scenario, trial.participant_configuration_results
        ),
        release=NativeTrialRelease(
            started.runtime, native, _release_policy(started)
        ),
        bindings={
            native_participant_address(binding): binding for binding in native.bindings
        },
        episode_seconds=_episode_seconds(native.bindings),
        store=store,
    )


def _release_policy(
    started: StartedTrialRuntime,
) -> ParticipantAutonomousExecutionRuntime:
    """Return the one native participant release policy of the execution plan."""
    specifications = started.admitted.execution_plan.model.behavior_specifications
    policies = [
        spec.autonomous_execution
        for spec in specifications.values()
        if spec.autonomous_execution is not None
    ]
    if len(policies) != 1:
        raise ValueError("this trial requires one native participant release policy")
    return policies[0]


def _episode_seconds(bindings: tuple[LilraeParticipantBinding, ...]) -> int:
    """Return the one episode bound that every installed participant shares."""
    durations = {binding.execution_binding.timeout_seconds for binding in bindings}
    if len(durations) != 1:
        raise ValueError("the participants must share the admitted episode bound")
    return durations.pop()


def _release_with_capture(
    root: Path,
    config: AptlConfig,
    attempt: TrialAttempt,
    progress: Callable[[str], None],
    started: StartedTrialRuntime,
    inputs: _AdmittedTrialInputs,
) -> tuple[TrialRecord, AcquisitionResult]:
    """Release the participants inside required capture and drain them."""
    admitted = started.admitted
    evidence: dict[str, Mapping[str, object]] = {}
    sessions: dict[str, Mapping[str, object]] = {}
    records: list[TrialRecord] = []

    def sink(address: str, item: OpenCodeInvocationEvidence) -> None:
        """Keep the allowlisted invocation facts of one participant."""
        evidence[address] = invocation_fields(item)

    def transcript_sink(address: str, session: Mapping[str, object]) -> None:
        """Keep the native session export of one participant."""
        sessions[address] = session

    def read_asset(asset: ParticipantControlContextAssetModel) -> bytes:
        """Read one admitted context asset from the installed pack."""
        return resolve_pack_artifact(
            str(admitted.bundle.root), asset.content.artifact_id
        ).data

    request = NativeEvidenceRequest(
        plan=inputs.plan,
        backend=started.backend,
        realization=admitted.realization,
        project_dir=root,
        environment=load_dotenv(root / ".env"),
        run_store=inputs.store,
        run_id=attempt.run_id,
        capture_selection=admitted.capture_selection,
    )
    progress(f"Preparing {len(inputs.participants)} native trial participants.")
    with (
        _termination_stops() as terminated,
        trial_executors(
            inputs.scenario,
            inputs.participants,
            attempt=attempt,
            bindings=inputs.bindings,
            settings=_launch_settings(root, config, attempt),
            read_asset=read_asset,
            sinks=TrialSinks(sink, transcript_sink),
        ) as executors,
    ):
        control = TrialControl(root)

        def execute() -> None:
            """Run the declared participants, then report the trial window."""
            records.append(
                run_declared_trial(
                    DeclaredTrial(
                        attempt,
                        inputs.scenario_sha256,
                        inputs.participants,
                        inputs.episode_seconds,
                    ),
                    release=inputs.release,
                    invocations=executors,
                    evidence=evidence,
                    store=inputs.store,
                    supervision=TrialSupervision(
                        lambda: terminated.is_set() or control.stop_requested(),
                        lambda: datetime.now(UTC),
                    ),
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
                    sessions, tuple(inputs.bindings)
                ),
                AUDIT_REGISTRATION: host_audit_source(),
            },
            trial_body=execute,
        )
    if len(records) != 1:
        raise RuntimeError(
            "required capture refused the trial before participant release"
        )
    return records[0], capture


def _evaluate_trial(
    started: StartedTrialRuntime,
    store: LocalRunStore,
    run_id: str,
    capture: AcquisitionResult,
) -> str:
    """Evaluate the captured evidence, record the results and return the outcome."""
    from aptl.backends.raes_evaluator import refresh_evidence_truth
    from aptl.backends.raes_repro import runtime_snapshot_record_payload

    admitted = started.admitted
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
        run_id,
        "trial/evaluation.json",
        {
            "objectives": objectives,
            "proposition_truth_results": dict(snapshot.proposition_truth_results),
        },
    )
    store.create_run_json_once(
        run_id,
        "trial/evaluated-runtime.json",
        {
            "redaction_policy": "redact_secrets",
            "snapshot": redact(runtime_snapshot_record_payload(snapshot)),
        },
    )
    return _outcome_status(objectives)


def _outcome_status(objectives: Mapping[str, Mapping[str, object]]) -> str:
    """Classify the objective verdicts; any missing verdict is inconclusive."""
    values = [item.get("passed") for item in objectives.values()]
    if not values or any(value is None for value in values):
        return "inconclusive"
    if all(values):
        return "succeeded"
    return "partial" if any(values) else "failed"


def _cleanup_fields(config: AptlConfig) -> dict[str, str]:
    """Report the provider credential cleanup that the trial record states."""
    cleanup = {"provider_access": "removed"}
    if isinstance(
        config.experiment.participant_credential_sources.vertex,
        AttachedServiceAccountSource,
    ):
        cleanup["vertex_access"] = "attached-service-account"
    return cleanup


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
