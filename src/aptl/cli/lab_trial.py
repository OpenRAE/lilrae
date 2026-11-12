"""Compose and run the trial that a started lab's SDL declares (#1670)."""

from __future__ import annotations

import hashlib
import shutil
import signal
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
import os
from typing import TYPE_CHECKING

from raes import parse_sdl_file
from raes_contracts.contracts import ParticipantControlContextAssetModel
from raes_env_packs import resolve_pack_artifact

from aptl.backends._raes_admission_helpers import bind_trial_unit
from aptl.backends._raes_scenario_resolution import resolve_scenario_bundle
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
from aptl.utils.logging import get_logger
from aptl.core.trial_attempt import TrialAttempt
from aptl.core.trial_control import TrialControl
from aptl.core.trial_record import TrialRecord, seal_trial_record
from aptl.core.trial_sdl import (
    TrialDeclarationError,
    admitted_participants,
    declared_participants,
)
from aptl.workbench.trial_launch import (
    TrialLaunchSettings,
    invocation_fields,
    trial_executors,
)
from aptl.workbench.trial_run import DeclaredTrial, run_declared_trial

if TYPE_CHECKING:
    from raes import Scenario
    from raes.scenario import InstantiatedScenario

    from aptl.core.scenario_bundle import ScenarioBundle

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
        record, gaps = _run_and_drain(
            root, config, config_path, attempt, scenario_path, scenario_sha256, progress
        )
        cleanup = {**record.cleanup, "transcripts": finalize_trial_capture(root)}
        record = record.model_copy(update={"cleanup": cleanup})
        seal_trial_record(
            LocalRunStore(_run_store_base(config_path.parent, config)),
            record,
            gaps=gaps,
        )
        progress(
            f"Trial ended by {record.terminal_cause}; run {record.run_id} is sealed."
        )
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
            {"address": item.address, "status": item.status}
            for item in record.participants
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
) -> tuple[TrialRecord, tuple[str, ...]]:
    """Run every participant, then remove its credentials; also return trial data gaps."""
    bundle = resolve_scenario_bundle(root, scenario_path, config)
    try:
        scenario, digest, configurations, bound = _trial_scenario(
            bundle, config, attempt
        )
        if digest != scenario_sha256:
            raise RuntimeError(
                "the trial SDL differs from the SDL that startup admitted"
            )
        participants = (
            admitted_participants(scenario, configurations)
            if configurations is not None
            else declared_participants(scenario)
        )
        if not participants:
            raise TrialDeclarationError(
                "the trial SDL declares no model-bearing participant"
            )
        evidence: dict[str, dict[str, object]] = {}

        def sink(address: str, item: OpenCodeInvocationEvidence) -> None:
            """Keep the latest allowlisted invocation facts of one participant."""
            evidence[address] = invocation_fields(item)

        store = LocalRunStore(_run_store_base(config_path.parent, config))

        def transcript_sink(address: str, session: Mapping[str, object]) -> None:
            """Retain one participant's redacted raw chat in the run before its seal."""
            store.create_run_json_once(
                attempt.run_id, f"trial/transcripts/{address}.json", session
            )

        def read_asset(asset: ParticipantControlContextAssetModel) -> bytes:
            """Read one prompt asset from the scenario pack by its artifact ID."""
            return resolve_pack_artifact(
                str(bundle.root), asset.content.artifact_id
            ).data

        progress(f"Starting {len(participants)} trial participants.")
        with (
            _termination_stops() as terminated,
            trial_executors(
                scenario,
                participants,
                attempt=attempt,
                settings=_launch_settings(root, config, attempt),
                read_asset=read_asset,
                evidence_sink=sink,
                transcript_sink=transcript_sink,
            ) as executors,
        ):
            control = TrialControl(root)
            record = run_declared_trial(
                DeclaredTrial(
                    attempt,
                    scenario_sha256,
                    participants,
                    config.experiment.trial_episode_seconds,
                ),
                invocations=executors,
                evidence=evidence,
                stop_requested=lambda: terminated.is_set() or control.stop_requested(),
                store=store,
                clock=lambda: datetime.now(UTC),
            )
        gaps: tuple[str, ...] = ()
        try:
            _retain_trial_end_data(root, config, bound, scenario, store, record)
        except Exception as exc:
            # Trial-end data never blocks the seal; the seal lists the gap.
            log.warning("trial-end data was not retained: %s", type(exc).__name__)
            gaps = (f"trial-end data capture failed: {type(exc).__name__}",)
        cleanup = {"provider_access": "removed"}
        # An attached account has no delivered key to remove; record that it was used.
        if isinstance(
            config.experiment.participant_credential_sources.vertex,
            AttachedServiceAccountSource,
        ) and any(item.model.startswith("google-vertex/") for item in participants):
            cleanup["vertex_access"] = "attached-service-account"
        return record.model_copy(update={"cleanup": cleanup}), gaps
    finally:
        bundle.close()


def _trial_scenario(
    bundle: ScenarioBundle, config: AptlConfig, attempt: TrialAttempt
) -> tuple[object, str, tuple | None, object]:
    """Return the scenario, its digest, any admitted configurations and the bound bundle.

    An admitted plan entry runs its instantiated snapshot with its participant
    configurations; otherwise the SDL file runs with its authored participants.
    """
    if attempt.unit is not None:
        bound = bind_trial_unit(bundle, config, attempt)
        trial = bound.trial
        assert trial is not None
        return (
            trial.scenario,
            trial.snapshot_digest,
            tuple(trial.participant_configuration_results),
            bound,
        )
    digest = "sha256:" + hashlib.sha256(bundle.sdl_path.read_bytes()).hexdigest()
    return parse_sdl_file(bundle.sdl_path), digest, None, bundle


def _retain_trial_end_data(
    root: Path,
    config: AptlConfig,
    bound: ScenarioBundle,
    scenario: Scenario | InstantiatedScenario,
    store: LocalRunStore,
    record: TrialRecord,
) -> None:
    """Keep the scenario's product dump and the host audit log before the seal."""
    from aptl.backends._raes_admission_helpers import resolve_admission_adapters
    from aptl.backends.trial_end_capture import retain_host_audit, retain_soc_dump
    from aptl.core.env import load_dotenv
    from aptl.core.lab import _configured_backend

    adapter = backend = None
    try:
        _, capture = resolve_admission_adapters(bound, config, None)
        adapter = capture.contribution.runtime_adapter if capture is not None else None
        backend, _failure = _configured_backend(root, config, command="trial")
    except Exception as exc:
        # A missing adapter is recorded, never fatal to the seal.
        log.warning("trial-end capture adapter is unavailable: %s", type(exc).__name__)
    env_path = root / ".env"
    retain_soc_dump(
        store,
        record.run_id,
        adapter=adapter,
        backend=backend,
        node_names=tuple(getattr(scenario, "nodes", {}) or {}),
        environment=load_dotenv(env_path) if env_path.is_file() else {},
    )
    retain_host_audit(
        store, record.run_id, started_at=record.started_at, ended_at=record.ended_at
    )


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
