"""No-follow snapshots of a run's retained artifact bytes."""

import hashlib
import os
import stat
from dataclasses import dataclass, field
from collections.abc import Iterator
from pathlib import Path
from typing import IO

from aptl.core.archival.seal import SealedArtifactSpec
from aptl.core.evidence.spool import SPOOL_SUBDIR, iter_spool, new_spool, spool_directory
from aptl.core.runstore import LocalRunStore
from aptl.utils.pathsafe import open_contained_nofollow, open_dir_contained_nofollow

_COPY_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class SnapshotArtifact:
    """One immutable copy of a run file, with its original run-relative path.

    The copy lives in an anonymous spool file, so a run of any size is
    archived in constant memory.
    """

    path: str
    sha256: str
    size: int
    spool: IO[bytes] = field(repr=False, compare=False)

    def chunks(self) -> Iterator[bytes]:
        """Yield the copied bytes from the start."""
        return iter_spool(self.spool)

    def specification(self) -> SealedArtifactSpec:
        media_type = {
            ".json": "application/json",
            ".jsonl": "application/x-ndjson",
        }.get(Path(self.path).suffix, "application/octet-stream")
        return SealedArtifactSpec(
            self.path,
            media_type,
            "retained-artifact",
            expected_sha256=self.sha256,
            expected_size_bytes=self.size,
        )


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int]:
    """Pin one file or directory observation to an unchanged object."""
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _copy_artifact(
    store: LocalRunStore, relative: Path, expected: os.stat_result
) -> SnapshotArtifact:
    """Copy the original descriptor into a spool and reject identity drift."""
    spool = new_spool()
    hasher = hashlib.sha256()
    size = 0
    with open_contained_nofollow(store.base_dir, relative) as source:
        before = os.fstat(source.fileno())
        if _file_identity(before) != _file_identity(expected):
            raise ValueError("trial-archive-source-changed")
        while chunk := source.read(_COPY_CHUNK):
            hasher.update(chunk)
            spool.write(chunk)
            size += len(chunk)
        after = os.fstat(source.fileno())
    if size != before.st_size or _file_identity(before) != _file_identity(after):
        raise ValueError("trial-archive-source-changed")
    spool.flush()
    return SnapshotArtifact(
        relative.relative_to(relative.parts[0]).as_posix(),
        hasher.hexdigest(),
        size,
        spool,
    )


def _directory_entries(
    store: LocalRunStore,
    directory: Path,
) -> Iterator[tuple[Path, os.stat_result]]:
    """Yield safe entries beneath one unchanged no-follow directory."""
    fd = open_dir_contained_nofollow(store.base_dir, directory)
    try:
        before = os.fstat(fd)
        with os.scandir(fd) as entries:
            for entry in entries:
                if "\\" in entry.name:
                    raise ValueError("trial-archive-source-unsafe")
                info = entry.stat(follow_symlinks=False)
                if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                    raise ValueError("trial-archive-source-unsafe")
                yield directory / entry.name, info
        if _file_identity(before) != _file_identity(os.fstat(fd)):
            raise ValueError("trial-archive-source-changed")
    finally:
        os.close(fd)


def _run_files(
    store: LocalRunStore,
    run_id: str,
) -> Iterator[tuple[Path, os.stat_result]]:
    """Walk every directory of one run."""
    pending = [Path(run_id)]
    while pending:
        directory = pending.pop()
        for relative, info in _directory_entries(store, directory):
            if stat.S_ISDIR(info.st_mode):
                pending.append(relative)
            else:
                yield relative, info


def snapshot_run_files(
    store: LocalRunStore, run_id: str
) -> tuple[SnapshotArtifact, ...]:
    """Copy every file of this run, refusing unsafe entries and changing files."""
    store.get_run_path(run_id)
    artifacts: list[SnapshotArtifact] = []
    with (
        spool_directory(store.base_dir / SPOOL_SUBDIR),
        store.finalization_lock(run_id),
    ):
        for relative, info in _run_files(store, run_id):
            artifacts.append(_copy_artifact(store, relative, info))
    return tuple(sorted(artifacts, key=lambda artifact: artifact.path))
