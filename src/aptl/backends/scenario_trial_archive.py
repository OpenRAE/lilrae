"""Retain exact admitted trial input through the protected local run store."""

from __future__ import annotations

from pathlib import Path
import os
import stat

from aptl.backends.scenario_family import AdmittedFamilyTrial
from aptl.core.runstore import LocalRunStore, RunStorageBackend
from aptl.utils.pathsafe import (
    PathContainmentError,
    create_exclusive_nofollow,
    open_contained_nofollow,
)


def archive_family_trial(store: RunStorageBackend, trial: AdmittedFamilyTrial) -> None:
    """Publish immutable input before apply; keep sensitive bytes out of evidence."""

    if not isinstance(store, LocalRunStore):
        raise ValueError("family-trial-local-storage-required")
    run_id = trial.provenance.run_id
    try:
        with store.finalization_lock(run_id):
            if store.is_sealed(run_id):
                raise ValueError("family-trial-run-sealed")
            store.create_run_json_once(run_id, "trial/identity.json", trial.evidence())
            _publish_snapshot(store, run_id, trial.snapshot)
    except (OSError, ValueError, RuntimeError, PathContainmentError) as exc:
        if str(exc) in {"family-trial-run-sealed", "family-trial-archive-conflict"}:
            raise
        raise ValueError("family-trial-archive-failed") from None


def _publish_snapshot(store: LocalRunStore, run_id: str, snapshot: bytes) -> None:
    """Publish once, accepting only an identical protected existing file."""

    path = Path(run_id) / "trial/instantiated-snapshot.json"
    try:
        create_exclusive_nofollow(store.base_dir, path, snapshot)
    except FileExistsError:
        with open_contained_nofollow(store.base_dir, path) as handle:
            info = os.fstat(handle.fileno())
            identical = (
                stat.S_ISREG(info.st_mode)
                and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_size == len(snapshot)
                and handle.read(len(snapshot) + 1) == snapshot
            )
        if not identical:
            raise ValueError("family-trial-archive-conflict") from None
