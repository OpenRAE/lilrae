"""Bounded no-follow snapshots of a run's retained artifact bytes."""

import hashlib
import os
import stat
from dataclasses import dataclass
from collections.abc import Iterator
from pathlib import Path

from aptl.core.archival.seal import SealedArtifactSpec
from aptl.core.runstore import LocalRunStore
from aptl.utils.pathsafe import open_contained_nofollow, open_dir_contained_nofollow


@dataclass(frozen=True)
class SnapshotLimits:
    """Installed archive limits refuse excess rather than truncate evidence."""

    max_file_bytes: int = 64 * 1024 * 1024
    max_total_bytes: int = 256 * 1024 * 1024
    max_files: int = 4096
    max_directories: int = 1024
    max_depth: int = 16

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 1 for value in vars(self).values()):
            raise ValueError("trial-archive-limits-invalid")


@dataclass(frozen=True)
class SnapshotArtifact:
    """One immutable byte snapshot, with its original run-relative path."""

    path: str
    data: bytes

    def specification(self) -> SealedArtifactSpec:
        media_type = {
            ".json": "application/json",
            ".jsonl": "application/x-ndjson",
        }.get(Path(self.path).suffix, "application/octet-stream")
        return SealedArtifactSpec(
            self.path,
            media_type,
            "retained-artifact",
            expected_sha256=hashlib.sha256(self.data).hexdigest(),
            expected_size_bytes=len(self.data),
        )


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int]:
    """Pin one file or directory observation to an unchanged object."""
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _read_artifact(
    store: LocalRunStore, relative: Path, expected: os.stat_result, limit: int
) -> bytes:
    """Read the bounded original descriptor and reject identity drift."""
    with open_contained_nofollow(store.base_dir, relative) as source:
        before = os.fstat(source.fileno())
        if _file_identity(before) != _file_identity(expected):
            raise ValueError("trial-archive-source-changed")
        data = source.read(limit + 1)
        after = os.fstat(source.fileno())
    if len(data) > limit or _file_identity(before) != _file_identity(after):
        raise ValueError("trial-archive-source-changed")
    return data


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
    limits: SnapshotLimits,
) -> Iterator[tuple[Path, os.stat_result]]:
    """Walk one run while enforcing directory count and depth limits."""
    pending = [(Path(run_id), 0)]
    directories = 1
    while pending:
        directory, depth = pending.pop()
        for relative, info in _directory_entries(store, directory):
            if stat.S_ISDIR(info.st_mode):
                directories += 1
                if directories > limits.max_directories or depth >= limits.max_depth:
                    raise ValueError("trial-archive-directory-limit")
                pending.append((relative, depth + 1))
            else:
                yield relative, info


def snapshot_run_files(
    store: LocalRunStore, run_id: str, *, limits: SnapshotLimits = SnapshotLimits()
) -> tuple[SnapshotArtifact, ...]:
    """Read only this run, refusing unsafe entries, changing files and excess."""
    store.get_run_path(run_id)
    artifacts: list[SnapshotArtifact] = []
    total = 0
    with store.finalization_lock(run_id):
        for relative, info in _run_files(store, run_id, limits):
            if len(artifacts) >= limits.max_files:
                raise ValueError("trial-archive-file-limit")
            available = min(limits.max_file_bytes, limits.max_total_bytes - total)
            if info.st_size > available:
                raise ValueError("trial-archive-byte-limit")
            data = _read_artifact(store, relative, info, available)
            total += len(data)
            artifacts.append(
                SnapshotArtifact(relative.relative_to(run_id).as_posix(), data)
            )
    return tuple(sorted(artifacts, key=lambda artifact: artifact.path))
