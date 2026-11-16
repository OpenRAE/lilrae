"""Bounded, no-follow source reads shared by the closure and archive builders.

One place that maps :mod:`aptl.utils.pathsafe` containment errors into the
missing/rejected distinction and applies an optional byte bound while
streaming from the single contained handle — so neither the closure nor the archive
reintroduces its own path reader (EXP-008 preflight: reuse the containment
helper, do not duplicate validators).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO

from aptl.utils import pathsafe

_READ_CHUNK = 1024 * 1024


class SourceMissing(Exception):
    """The source path does not exist under the run root."""


class SourceRejected(Exception):
    """The source exists but violates containment/shape/size rules."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def _open(run_dir: Path, relpath: str) -> BinaryIO:
    """Open ``relpath`` under ``run_dir`` no-follow, mapping containment errors."""
    try:
        return pathsafe.open_contained_nofollow(run_dir, relpath)
    except pathsafe.PathContainmentError as exc:
        if exc.reason == pathsafe.REASON_NOT_FOUND:
            raise SourceMissing() from exc
        raise SourceRejected(exc.reason) from exc


def _stream(
    handle: BinaryIO, *, max_bytes: int | None, keep_body: bool
) -> tuple[str, int, bytes]:
    """Hash a handle to ``sha256:<hex>`` and its size, optionally retaining bytes."""
    digest = hashlib.sha256()
    size = 0
    body = bytearray()
    while True:
        chunk = handle.read(_READ_CHUNK)
        if not chunk:
            break
        size += len(chunk)
        if max_bytes is not None and size > max_bytes:
            raise SourceRejected("source exceeds member byte limit")
        digest.update(chunk)
        if keep_body:
            body.extend(chunk)
    return f"sha256:{digest.hexdigest()}", size, bytes(body)


def hash_source(
    run_dir: Path, relpath: str, *, max_bytes: int | None = None
) -> tuple[str, int]:
    """Return ``(sha256:<hex>, size)`` of ``relpath`` without buffering it whole."""
    with _open(run_dir, relpath) as handle:
        digest, size, _ = _stream(handle, max_bytes=max_bytes, keep_body=False)
    return digest, size


def read_source(
    run_dir: Path, relpath: str, *, max_bytes: int | None = None
) -> tuple[str, int, bytes]:
    """Return ``(sha256:<hex>, size, bytes)`` of ``relpath``.

    ``max_bytes`` bounds only reads of untrusted input; ``None`` reads it all.
    """
    with _open(run_dir, relpath) as handle:
        return _stream(handle, max_bytes=max_bytes, keep_body=True)


__all__ = ["SourceMissing", "SourceRejected", "hash_source", "read_source"]
