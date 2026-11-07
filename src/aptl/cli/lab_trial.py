"""Compose and run the trial that a started lab's SDL declares (#1670)."""

from __future__ import annotations

import hashlib
import shutil
import signal
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
import os

from raes import parse_sdl_file
from raes_contracts.contracts import ParticipantControlContextAssetModel
from raes_env_packs import resolve_pack_artifact

from aptl.backends._raes_scenario_resolution import resolve_scenario_bundle
from aptl.core.config import AptlConfig, find_config, load_config
from aptl.core.lab import finalize_trial_capture
from aptl.core.mcp_policy import configured_server_ids
from aptl.core.opencode import OpenCodeInvocationEvidence
from aptl.core.runstore import LocalRunStore
from aptl.core.trial_attempt import TrialAttempt
from aptl.core.trial_control import TrialControl
from aptl.core.trial_record import TrialRecord, seal_trial_record
from aptl.core.trial_sdl import TrialDeclarationError, declared_participants
from aptl.workbench.trial_launch import TrialLaunchSettings, invocation_fields, trial_executors
from aptl.workbench.trial_run import DeclaredTrial, run_declared_trial

__all__ = ["refuse_existing_trial_run", "run_lab_trial", "trial_summary"]

_WORK_DIR = Path(".aptl/trial-work")


def refuse_existing_trial_run(project_dir: Path, attempt: TrialAttempt) -> None:
    """Refuse a run ID that already names a run, before any lab change."""
    config_path = find_config(project_dir)
    config = load_config(config_path) if config_path is not None else AptlConfig()
    base = _run_store_base(config_path.parent if config_path else project_dir, config)
    if (base / attempt.run_id).exists():
        raise ValueError(f"run {attempt.run_id} already exists; a trial needs a new run ID")


def run_lab_trial(
    project_dir: Path,
    attempt: TrialAttempt,
    *,
    scenario_path: Path | None,
    scenario_sha256: str,
    progress: Callable[[str], None],
) -> TrialRecord:
    """Run the declared participants on the started lab and seal the run.

    The trial refuses an SDL whose digest differs from the one startup admitted.
    """
    root = project_dir.resolve()
    config_path = find_config(root)
    if config_path is None:
        raise ValueError("aptl.json is required for a trial")
    config = load_config(config_path)
    control = TrialControl(root)
    control.begin(attempt)
    try:
        record = _run_and_drain(root, config, config_path, attempt, scenario_path, scenario_sha256, progress)
        cleanup = {**record.cleanup, "transcripts": finalize_trial_capture(root)}
        record = record.model_copy(update={"cleanup": cleanup})
        seal_trial_record(LocalRunStore(_run_store_base(config_path.parent, config)), record)
        progress(f"Trial ended by {record.terminal_cause}; run {record.run_id} is sealed.")
        return record
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
            {"address": item.address, "status": item.status} for item in record.participants
        ],
        "cleanup": dict(record.cleanup),
    }


def _run_and_drain(
    root: Path,
    config: AptlConfig,
    config_path: Path,
    attempt: TrialAttempt,
    scenario_path: Path | None,
    scenario_sha256: str,
    progress: Callable[[str], None],
) -> TrialRecord:
    """Run every participant, then remove its credentials before returning."""
    bundle = resolve_scenario_bundle(root, scenario_path, config)
    try:
        sdl = bundle.sdl_path.read_bytes()
        if "sha256:" + hashlib.sha256(sdl).hexdigest() != scenario_sha256:
            raise RuntimeError("the trial SDL differs from the SDL that startup admitted")
        scenario = parse_sdl_file(bundle.sdl_path)
        participants = declared_participants(scenario)
        if not participants:
            raise TrialDeclarationError("the trial SDL declares no model-bearing participant")
        evidence: dict[str, dict[str, object]] = {}

        def sink(address: str, item: OpenCodeInvocationEvidence) -> None:
            """Keep the latest allowlisted invocation facts of one participant."""
            evidence[address] = invocation_fields(item)

        def read_asset(asset: ParticipantControlContextAssetModel) -> bytes:
            """Read one prompt asset from the scenario pack by its artifact ID."""
            return resolve_pack_artifact(str(bundle.root), asset.content.artifact_id).data

        progress(f"Starting {len(participants)} trial participants.")
        with _termination_stops() as terminated, trial_executors(
            scenario,
            participants,
            run_id=attempt.run_id,
            deadline=attempt.deadline,
            settings=_launch_settings(root, config, attempt),
            read_asset=read_asset,
            evidence_sink=sink,
        ) as executors:
            control = TrialControl(root)
            record = run_declared_trial(
                DeclaredTrial(attempt, scenario_sha256, participants),
                invocations=executors,
                evidence=evidence,
                stop_requested=lambda: terminated.is_set() or control.stop_requested(),
                store=LocalRunStore(_run_store_base(config_path.parent, config)),
                clock=lambda: datetime.now(UTC),
            )
        return record.model_copy(update={"cleanup": {"provider_access": "removed"}})
    finally:
        bundle.close()


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


def _launch_settings(root: Path, config: AptlConfig, attempt: TrialAttempt) -> TrialLaunchSettings:
    """Collect the operator settings that every participant launch uses."""
    executable = config.experiment.opencode_executable
    if executable is None:
        raise ValueError("aptl.json experiment.opencode_executable must name the OpenCode build")
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
