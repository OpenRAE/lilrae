"""Stream content-addressed files under a base directory in constant memory.

The final name of a content-addressed file is its SHA-256 digest, which is
known only after the last byte arrives. Chunks are therefore written to a
fresh temporary inode while the digest accumulates, the inode is synced, and
then it is linked to its digest name with no-replace semantics. The same
no-follow directory walk as :mod:`aptl.utils.pathsafe` applies.

Disk exhaustion is never handled by cutting content. The caller supplies a
free-space reserve. When writing would leave less than that fraction of the
filesystem free, the write fails with :class:`FreeSpaceReserveError` and the
temporary inode is removed.
"""

from __future__ import annotations

import errno
import hashlib
import os
from collections.abc import Iterable
from pathlib import Path

from aptl.utils._pathsafe_core import (
    _open_base_fd,
    _open_dir_nofollow_or_create,
    _split_components,
    _walk_to_parent,
)
from aptl.utils.pathsafe import (
    _TMP_COUNTER,
    _create_temp_leaf,
    _discard_temp_leaf,
    write_all,
)

#: Bytes written between two free-space checks.
_RESERVE_CHECK_INTERVAL = 64 * 1024 * 1024
_READ_CHUNK = 1024 * 1024


class FreeSpaceReserveError(OSError):
    """A write would leave less free space than the configured reserve."""

    def __init__(self) -> None:
        super().__init__(errno.ENOSPC, "run store free-space reserve reached")


def require_free_space(fd: int, reserve_fraction: float) -> None:
    """Raise when the filesystem of ``fd`` has less than the reserve free."""
    info = os.fstatvfs(fd)
    if info.f_bavail < info.f_blocks * reserve_fraction:
        raise FreeSpaceReserveError()


def _digest_of(parent_fd: int, name: str) -> tuple[str, int]:
    """Return the SHA-256 hex digest and size of one existing regular leaf."""
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(name, flags, dir_fd=parent_fd)
    hasher = hashlib.sha256()
    size = 0
    with os.fdopen(fd, "rb") as handle:
        while chunk := handle.read(_READ_CHUNK):
            hasher.update(chunk)
            size += len(chunk)
    return hasher.hexdigest(), size


def _stream_to_temp(
    parent_fd: int, chunks: Iterable[bytes], reserve_fraction: float
) -> tuple[str, str, int]:
    """Write ``chunks`` to a synced temporary inode; return name, digest, size."""
    tmp_fd, tmp_name = _create_temp_leaf(
        f".content.{os.getpid()}.{next(_TMP_COUNTER)}.tmp", parent_fd
    )
    hasher = hashlib.sha256()
    size = 0
    next_check = 0
    try:
        try:
            for chunk in chunks:
                if size >= next_check:
                    require_free_space(tmp_fd, reserve_fraction)
                    next_check = size + _RESERVE_CHECK_INTERVAL
                hasher.update(chunk)
                write_all(tmp_fd, chunk)
                size += len(chunk)
            os.fsync(tmp_fd)
        finally:
            os.close(tmp_fd)
    except BaseException:
        _discard_temp_leaf(tmp_name, parent_fd)
        raise
    return tmp_name, hasher.hexdigest(), size


def create_exclusive_stream_nofollow(
    base_dir: Path | str,
    relative_path: str | Path,
    chunks: Iterable[bytes],
    *,
    reserve_fraction: float,
) -> tuple[str, int]:
    """Stream ``chunks`` to a new file; return its SHA-256 digest and size.

    An existing file is accepted only when its digest and size agree; any
    other existing content raises ``FileExistsError``.
    """
    components = _split_components(relative_path)
    base_fd = _open_base_fd(base_dir)
    parent_fd = base_fd
    try:
        parent_fd = _walk_to_parent(
            components[:-1], base_fd, open_dir=_open_dir_nofollow_or_create
        )
        tmp_name, digest, size = _stream_to_temp(parent_fd, chunks, reserve_fraction)
        try:
            os.link(
                tmp_name,
                components[-1],
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            if _digest_of(parent_fd, components[-1]) != (digest, size):
                raise
        finally:
            _discard_temp_leaf(tmp_name, parent_fd)
        os.fsync(parent_fd)
        return digest, size
    finally:
        if parent_fd != base_fd:
            os.close(parent_fd)
        os.close(base_fd)


def create_content_addressed_nofollow(
    base_dir: Path | str,
    directory: str | Path,
    chunks: Iterable[bytes],
    *,
    reserve_fraction: float,
) -> tuple[str, int]:
    """Stream ``chunks`` to ``<directory>/<sha256-hex>``; return digest and size.

    A file that already has the digest name is accepted only when its own
    digest and size agree. Any other existing content raises
    ``FileExistsError``.
    """
    components = _split_components(directory)
    base_fd = _open_base_fd(base_dir)
    parent_fd = base_fd
    try:
        parent_fd = _walk_to_parent(
            components, base_fd, open_dir=_open_dir_nofollow_or_create
        )
        tmp_name, digest, size = _stream_to_temp(parent_fd, chunks, reserve_fraction)
        try:
            os.link(
                tmp_name,
                digest,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            if _digest_of(parent_fd, digest) != (digest, size):
                raise
        finally:
            _discard_temp_leaf(tmp_name, parent_fd)
        os.fsync(parent_fd)
        if _digest_of(parent_fd, digest) != (digest, size):
            raise OSError(errno.EIO, "content-addressed post-write verification failed")
        return digest, size
    finally:
        if parent_fd != base_fd:
            os.close(parent_fd)
        os.close(base_fd)
