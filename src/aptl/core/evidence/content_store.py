"""Content-addressed + run-scoped create-once evidence persistence (EXP-010 /
issue #752 preflight "Evidence ownership and persistence").

The preflight requires the ``RunStorageBackend`` boundary to be EXTENDED
narrowly for streamed content-addressed blob insertion and run-scoped
create-once canonical JSON — NOT a second evidence repository beside
``LocalRunStore``. These functions are that narrow extension: they operate on
the injected store (via its public ``base_dir`` / ``get_run_path``) and reuse
the store's own ID/path validation, canonicalization and no-follow/create-exclusive
primitives. The coordinator derives every location
from a validated id + the computed digest; a plugin never supplies a path.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from aptl.core.runstore import (
    LocalRunStore,
    RunStoreConflictError,
    _validate_id,
    _validate_relative_path,
)
from aptl.utils.pathsafe_stream import create_content_addressed_nofollow


@dataclass(frozen=True)
class ContentInsertion:
    """The result of a content-addressed evidence blob insertion.

    ``relative_path`` is the run-relative POSIX path of the stored object
    (``<subdir>/<sha256-hex>``); ``digest`` is its ``sha256:<hex>`` prefixed
    digest; ``size`` is the number of bytes stored. The stored object is
    always the complete source content.
    """

    relative_path: str
    digest: str
    size: int


def create_content_addressed(
    store: LocalRunStore, run_id: str, chunks: Iterable[bytes], *, subdir: str
) -> ContentInsertion:
    """Stream ``chunks`` into a content-addressed blob under ``<run_id>/<subdir>/<sha256-hex>``.

    Memory use does not depend on the content size. The store's free-space
    reserve applies while the bytes are written. A repeated digest is
    idempotent only when the existing bytes agree; a collision with different
    bytes fails closed.
    """
    safe_run_id = _validate_id(run_id, "run_id")
    safe_subdir = _validate_relative_path(subdir)
    base_dir = store.base_dir
    base_dir.mkdir(parents=True, exist_ok=True)
    # Acquire the per-run lock and recheck seal state so a content-addressed
    # insertion cannot add bytes to a run being (or already) sealed by another
    # writer (ADR-050 write/seal exclusion).
    with store.finalization_lock(run_id):
        store._reject_if_sealed(run_id, safe_subdir)
        try:
            digest_hex, size = create_content_addressed_nofollow(
                base_dir,
                f"{safe_run_id}/{safe_subdir}",
                chunks,
                reserve_fraction=store.free_space_reserve,
            )
        except FileExistsError:
            raise RunStoreConflictError(
                f"create_content_addressed digest collision with different bytes: {run_id}/{safe_subdir}"
            ) from None
    return ContentInsertion(
        relative_path=f"{safe_subdir}/{digest_hex}",
        digest=f"sha256:{digest_hex}",
        size=size,
    )


def create_run_json_once(store: LocalRunStore, run_id: str, relative_path: str, payload: object) -> Path:
    """Create-once, canonical, no-follow JSON persistence UNDER the run dir.

    Delegates to :meth:`LocalRunStore.create_run_json_once` (ADR-050
    consolidation) so it inherits the per-run finalization lock and sealed-state
    recheck — a create-once write can never add a file to a run being or already
    sealed, and the reserved marker path is refused here too.
    """
    return store.create_run_json_once(run_id, relative_path, payload)
