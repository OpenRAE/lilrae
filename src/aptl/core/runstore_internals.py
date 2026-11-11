"""Internal helpers and shared state for :mod:`aptl.core.runstore`.

Split out of ``runstore.py`` (which owns the :class:`LocalRunStore` filesystem
implementation) so the module stays focused: this file holds the id/path
validators, the create-once canonicalization + secret-invariant helpers, the
per-run lock registry, the create-once error taxonomy, the cross-process
run-dir resolution, and the owner-only mode helpers. ``runstore`` re-imports
and re-exports these, so existing ``from aptl.core.runstore import ...`` call
sites are unaffected.
"""

import errno
import json
import os
import re
import shutil
import stat
import threading
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, TypedDict

import rfc8785

from aptl.utils.logging import get_logger
from aptl.utils.redaction import redact

log = get_logger("runstore")

#: ADR-033 "Security layers": run captures are readable only by the owning
#: user, so every directory the store creates is ``0700`` and every file
#: ``0600``. A requested mode without group or other bits stays clear of them
#: under any umask. On non-POSIX hosts the modes are ignored and the
#: tightening steps below are no-ops.
_PRIVATE_DIR_MODE = 0o700
_PRIVATE_FILE_MODE = 0o600
_GROUP_OTHER = 0o077

#: ``open`` errors that mean "nothing to tighten here": the entry is missing,
#: is not a directory, is a symlink (``O_NOFOLLOW``), or cannot be opened.
_SKIP_RESTRICT_ERRNOS = frozenset(
    {errno.ENOENT, errno.ENOTDIR, errno.ELOOP, errno.EACCES, errno.EPERM}
)


class RunManifest(TypedDict):
    """Metadata manifest for a single experiment run."""

    run_id: str
    scenario_id: str
    scenario_name: str
    started_at: str
    finished_at: str
    duration_seconds: float
    trace_id: str
    config_snapshot: dict[str, Any]
    containers: list[str]
    flags_captured: int


@dataclass
class _HeldLock:
    """A held per-run finalization lock: its file descriptor and reentrancy depth."""

    fd: int
    depth: int


#: Process-wide registry of held per-run locks, keyed by
#: ``(base_dir, run_id, thread_id)``. Reentrancy is per THREAD: the same thread
#: nesting acquisitions (a coordinator holding the lock while its create-once
#: manifest write re-acquires it) reuses one ``flock``; a different thread or
#: process opens its own descriptor and blocks on ``flock`` until released. This
#: makes every run-directory mutation mutually exclusive with finalization
#: without the coordinator deadlocking on itself.
_LOCK_REGISTRY: dict[tuple[str, str, int], _HeldLock] = {}
_LOCK_REGISTRY_GUARD = threading.Lock()


class SecretInvariantError(ValueError):
    """Raised by :meth:`LocalRunStore.create_json_once` when applying the
    shared secret-classification policy (:mod:`aptl.utils.redaction`) would
    change the payload.

    ADR-047 "Persistence and state model": the create-once operation must
    preserve semantic bytes exactly. It must never silently persist a
    payload that differs from what was approved for execution, so a
    payload containing identity-bearing secret-shaped content is rejected
    outright rather than redacted-and-written.
    """


class RunStoreConflictError(ValueError):
    """Raised by the create-once persistence paths (``create_json_once`` and
    the run-scoped / content-addressed extensions in
    :mod:`aptl.core.evidence.content_store`) when the target already exists
    with bytes that differ from those being written.

    A byte-identical existing payload is treated as idempotent success
    (ADR-047); only a genuine mismatch is an error.
    """


class SealedRunError(RuntimeError):
    """Raised when a mutable write targets an already-sealed run archive.

    ADR-050 "A seal marker is the atomic commit point": once the run's seal
    marker exists, every structured, opaque, and export path must treat the
    archive as immutable. Overwrite-capable writers refuse rather than mutate
    sealed bytes; a correction is a new run version, never an in-place edit.
    """


# OBS-003: run / session identifiers become directory components, so they
# must be filesystem-safe. ``trace_id`` from ``trace-context.json`` is hex
# (matches the pattern by construction), but ``session_id`` is produced
# by the MCP server and could in principle drift. Reject anything that
# could break out of the runs/ tree.
# Allow leading `_` so the `_unbound` sentinel (used when MCP servers run
# outside an active scenario context) survives validation. No traversal
# vector — `_` is just a filename character. With `re.ASCII`, `\w` is
# `[A-Za-z0-9_]` (SonarCloud S6353 — concise character class). Without the
# flag, `\w` also matches non-ASCII letters and digits, which the capture
# broker, the capture writer and the MCP `ID_RE` all reject.
_ID_RE = re.compile(r"^\w[\w.-]*$", re.ASCII)


def _validate_id(value: str, kind: str) -> str:
    """Reject anything that could break out of the ``runs/`` tree.

    Returns the value unchanged when it matches the canonical id
    contract (``^\\w[\\w.-]*$`` AND does not contain ``..``); raises
    ``ValueError`` otherwise. ``kind`` is included in the error
    message so callers see e.g. ``invalid trace_id: '../escape'``.
    """
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ValueError(f"invalid {kind}: {value!r}")
    if ".." in value:
        # `..` survives the character-class regex (dots are allowed for
        # e.g. semantic-version-shaped ids) but is the canonical
        # path-traversal segment. Reject defensively.
        raise ValueError(f"invalid {kind} (contains '..'): {value!r}")
    return value


def _validate_relative_path(relative_path: str) -> str:
    """Reject relative paths that could escape a run directory."""
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError(f"invalid relative_path: {relative_path!r}")
    if Path(relative_path).is_absolute():
        raise ValueError(f"invalid relative_path (absolute): {relative_path!r}")
    parts = PurePosixPath(relative_path.replace("\\", "/")).parts
    if ".." in parts:
        raise ValueError(
            f"invalid relative_path (contains '..'): {relative_path!r}"
        )
    return relative_path


def _canonicalize_payload(payload: object) -> tuple[bytes, object]:
    """Return ``(RFC 8785 canonical bytes, JSON-round-tripped structure)``
    for :meth:`LocalRunStore.create_json_once`.

    The round-tripped structure is what is actually compared and
    persisted: a tuple normalizes to a list, and any value that is not
    already JSON-serializable is a caller bug, not something to silently
    stringify — ``create_json_once`` payloads are structured plan/trial
    projections, not free-form archive data, so (unlike :func:`_safe_default`
    below) no ``default=str`` escape hatch is offered here.
    """
    try:
        raw = json.dumps(payload)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"create_json_once payload is not JSON-serializable: {exc}") from exc
    normalized = json.loads(raw)
    return rfc8785.dumps(normalized), normalized


def _assert_no_secret_drift(normalized: object) -> None:
    """Reject ``normalized`` if the shared :func:`redact` policy would
    change it at all (ADR-047 create-once secret invariant).

    Reuses the exact production :func:`redact` — the same classification
    :func:`aptl.utils.redaction.is_sensitive_key` and
    :func:`aptl.utils.redaction.is_secret_shaped_value` are built from — so
    this can never silently drift out of lockstep with what actually gets
    redacted elsewhere.
    """
    if redact(normalized) != normalized:
        raise SecretInvariantError(
            "create_json_once payload contains identity-bearing content "
            "the shared secret-classification policy (aptl.utils.redaction) "
            "would change; rejecting rather than silently persisting a "
            "payload that differs from what was approved for execution"
        )


def _safe_default(obj: object) -> str:
    """``json.dumps`` ``default`` hook that stringifies AND redacts.

    Plain ``default=str`` would let any non-JSON-serializable value
    (an exception, a custom object, a ``Path`` whose ``__str__``
    contains an unexpected token) reach disk after :func:`redact`
    has already returned the structure — bypassing the redaction
    contract. Routing the produced string back through ``redact``
    closes that escape hatch (ADR-029).
    """
    return redact(str(obj))


def _restrict_fd(fd: int) -> None:
    """Clear group/other bits on an open entry the effective user owns.

    Clear-only and owner-only: an entry that is already private, or that
    belongs to another account (for example a seat run tree handed to the
    desktop user), is left as it is. A no-op without POSIX ``fchmod``.
    """
    if os.name != "posix" or not hasattr(os, "fchmod"):
        return
    status = os.fstat(fd)
    mode = stat.S_IMODE(status.st_mode)
    if mode & _GROUP_OTHER and status.st_uid == os.geteuid():
        os.fchmod(fd, mode & ~_GROUP_OTHER)


def _restrict_to_owner(directory: Path) -> None:
    """Tighten an existing store-owned directory to owner-only, best-effort.

    The directory is opened ``O_NOFOLLOW`` and re-moded through its
    descriptor, so a symlink is skipped and an entry swapped in after the
    check is never re-moded by path. A missing entry, a non-directory, or
    one that cannot be opened is skipped rather than raised; the write that
    follows then behaves as it did before this step existed.
    """
    if os.name != "posix":
        return
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        fd = os.open(directory, flags)
    except OSError as exc:
        if exc.errno in _SKIP_RESTRICT_ERRNOS:
            return
        raise
    try:
        _restrict_fd(fd)
    finally:
        os.close(fd)


def _mkdir_private(directory: Path) -> None:
    """Create one directory ``0700``; an existing directory is left as it is."""
    try:
        os.mkdir(directory, _PRIVATE_DIR_MODE)
    except FileExistsError:
        if not directory.is_dir():
            raise


def _make_private_dirs(directory: Path) -> None:
    """``mkdir -p`` that creates every missing component ``0700``.

    ``Path.mkdir(parents=True)`` and ``os.makedirs`` create missing parents
    with the umask's default mode, so missing ancestors (such as ``.aptl/``)
    would be group- or world-readable. Existing components are never
    re-moded.
    """
    try:
        _mkdir_private(directory)
    except FileNotFoundError:
        if directory.parent == directory:
            raise
        _make_private_dirs(directory.parent)
        _mkdir_private(directory)


def _private_store_entry(base_dir: Path, name: str) -> None:
    """Create ``base_dir`` owner-only and tighten its existing ``name`` entry."""
    _make_private_dirs(base_dir)
    _restrict_to_owner(base_dir / name)


def _make_private_run_dirs(base_dir: Path, run_id: str, *directories: Path) -> None:
    """Prepare ``base_dir/run_id`` and ``directories`` for a run write.

    Every directory the store creates is ``0700``, including missing
    ancestors of ``base_dir``; files are created ``0600`` through
    :func:`_private_opener`. On each write, the run, namespace or ``locks``
    directory written into and the written file lose group and other bits
    when the current user owns them. An existing ``base_dir`` and other
    existing entries keep their modes. The modes are defense in depth, not a
    substitute for the ADR-029 redaction at the persistence boundary.
    """
    _private_store_entry(base_dir, run_id)
    for directory in directories:
        _make_private_dirs(directory)


def _private_opener(path: str, flags: int) -> int:
    """``open`` opener: create files ``0600`` and tighten an existing one."""
    fd = os.open(path, flags, _PRIVATE_FILE_MODE)
    try:
        _restrict_fd(fd)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _require_regular_file(status: os.stat_result, path: Path, role: str) -> None:
    """Raise :class:`shutil.SpecialFileError` unless ``status`` is a regular file."""
    if not stat.S_ISREG(status.st_mode):
        raise shutil.SpecialFileError(f"copy_file {role} is not a regular file: {path}")


def _copy_private(source: Path, target: Path) -> None:
    """Copy ``source`` bytes and timestamps into an owner-only ``target``.

    Unlike ``shutil.copy2`` this copies neither the source's permission bits
    nor its flags or extended attributes (which can carry a POSIX access
    ACL), so a ``0644`` source lands ``0600``. The source is never modified.
    Only regular files are copied: a source or an existing target that is a
    FIFO, device, socket or directory raises :class:`shutil.SpecialFileError`
    before any byte is read or written. The source is opened non-blocking so
    a FIFO is refused instead of waiting for a writer.
    """
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(source, flags), "rb") as src:
        source_status = os.fstat(src.fileno())
        _require_regular_file(source_status, source, "source")
        try:
            target_status = os.stat(target)
        except FileNotFoundError:
            target_status = None
        if target_status is not None:
            _require_regular_file(target_status, target, "target")
        if target_status is not None and os.path.samestat(source_status, target_status):
            # copy2 refuses this too; truncating the target would lose the bytes.
            raise shutil.SameFileError(f"{source} and {target} are the same file")
        with open(target, "wb", opener=_private_opener) as dst:
            shutil.copyfileobj(src, dst)
        source_status = os.fstat(src.fileno())
    os.utime(target, ns=(source_status.st_atime_ns, source_status.st_mtime_ns))


# ---------------------------------------------------------------------------
# OBS-003: cross-process run-dir resolution.
# ---------------------------------------------------------------------------


def resolve_active_run_dir(state_dir: Path) -> Path | None:
    """Resolve the active scenario's run directory from ``trace-context.json``.

    ``state_dir`` is the APTL state directory (typically ``.aptl/`` at
    the repo root, or wherever ``APTL_STATE_DIR`` points). The function
    reads ``state_dir/trace-context.json`` (the same file the MCP
    servers read for trace correlation) and returns
    ``state_dir/runs/<trace_id>``.

    Returns ``None`` cleanly when:
    - the trace-context file is absent (no scenario active),
    - the file is malformed JSON,
    - the file is missing ``trace_id``, or
    - ``trace_id`` contains characters that could break out of the
      ``runs/`` tree (defence in depth — Python writes hex; this
      catches a tampered file).

    Callers decide what to do with ``None`` (write to an ``_unbound``
    sentinel, skip capture, or log).
    """
    ctx_file = state_dir / "trace-context.json"
    if not ctx_file.exists():
        return None
    # Single return on the failure path (SonarCloud S1142 — at most
    # 3 returns per function): build a `resolved` local and let
    # every error branch fall through to the final `return None`.
    resolved: Path | None = None
    try:
        data = json.loads(ctx_file.read_text(encoding="utf-8"))
        trace_id = data.get("trace_id") if isinstance(data, dict) else None
        if isinstance(trace_id, str):
            try:
                _validate_id(trace_id, "trace_id")
                resolved = state_dir / "runs" / trace_id
            except ValueError:
                log.warning("trace-context.json contained unsafe trace_id; ignoring")
    except (json.JSONDecodeError, OSError) as exc:
        log.debug("trace-context.json unreadable: %s", exc)
    return resolved
