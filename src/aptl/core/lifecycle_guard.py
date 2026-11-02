"""Shared project-wide ownership for mutating lab lifecycle operations.

The fixed ``.aptl/lifecycle/.lock`` file is only a rendezvous point. Ownership
comes from the operating system lock held on its descriptor, never from file
existence or persisted PID metadata. Acquisitions are non-blocking so callers
can return an actionable busy result instead of hanging behind a long startup.
"""

from __future__ import annotations

import errno
import os
import shlex
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from aptl.core._lifecycle_windows import (
    _windows_close_handle,
    _windows_handle_to_fd,
    _windows_open_relative_handle,
    _windows_open_root_handle,
    _windows_reject_reparse_point,
)
from aptl.core.config import find_config
from aptl.core.lifecycle_policy import LifecycleBusyError
from aptl.core.trial_ownership import TRIAL_FENCE, require_trial_owner, trial_fence_owner
from aptl.utils.pathsafe import PathContainmentError, open_dir_contained_nofollow

# Platform-specific import.
try:
    import fcntl
# Windows has no POSIX flock module.
except ModuleNotFoundError:
    fcntl = None

# Platform-specific import.
try:
    import msvcrt
# POSIX has no Microsoft C runtime module.
except ModuleNotFoundError:
    msvcrt = None

_LIFECYCLE_DIR = ".aptl/lifecycle"
_LOCK_FILE = ".lock"


class LifecycleLockUnavailableError(RuntimeError):
    """Raised when the owner lock cannot be established safely."""


def lifecycle_recovery_command(command: str, project_dir: Path | None) -> str:
    """Aim a recovery command at the lifecycle operation's canonical project."""
    if project_dir is None:
        return command
    root = canonical_lifecycle_project_root(project_dir)
    if root == canonical_lifecycle_project_root(Path(".")):
        return command
    return f"{command} --project-dir {shlex.quote(str(root))}"


def stop_recovery_routes(project_dir: Path | None) -> tuple[tuple[str, str], ...]:
    """Aim the shared stop commands at the lifecycle operation's project."""
    from aptl.core.lab_types import STOP_RECOVERY_ROUTES

    return tuple(
        (lifecycle_recovery_command(command, project_dir), effect)
        for command, effect in STOP_RECOVERY_ROUTES
    )


@dataclass
class _HeldLifecycleLock:
    """One process-local reference to an owned operating-system lock."""

    fd: int
    depth: int
    pid: int = field(default_factory=os.getpid)


_HELD_LOCKS: dict[tuple[str, int], _HeldLifecycleLock] = {}
_HELD_LOCKS_GUARD = threading.Lock()
_DELEGATED_LOCKS: ContextVar[dict[str, tuple[tuple[str, int], _HeldLifecycleLock]] | None] = (
    ContextVar("lifecycle_locks", default=None)
)


def canonical_lifecycle_project_root(project_dir: Path) -> Path:
    """Resolve the config-owning project root without mutating project state."""

    candidate = Path(project_dir).resolve()
    for directory in (candidate, *candidate.parents):
        if find_config(directory) is not None:
            return directory
    return candidate


@contextmanager
def lifecycle_mutation_lock(
    project_dir: Path, *, trial_owner: bytes | None = None
) -> Iterator[Path]:
    """Hold the project lifecycle owner lock, reentrant in the current thread.

    An unrelated thread or process receives :class:`LifecycleBusyError`
    immediately. Related worker callbacks inherit the live context. The lock
    file is created below the trusted project directory
    through descriptor-relative, no-follow path handling. POSIX locks are
    forced to owner-only permissions; Windows creation inherits the project's
    ACL while rejecting every reparse-point component by handle.
    """

    with placement_mutation_lock(
        canonical_lifecycle_project_root(project_dir), trial_owner=trial_owner
    ) as root:
        yield root


@contextmanager
def placement_mutation_lock(
    root: Path, *, trial_owner: bytes | None = None
) -> Iterator[Path]:
    """Lock an exact placement-state root, without discovering a config owner."""
    root = root.resolve()
    key = (str(root), threading.get_ident())
    delegated = (_DELEGATED_LOCKS.get() or {}).get(str(root))
    reused = False
    if delegated is not None:
        with _HELD_LOCKS_GUARD:
            if (
                _HELD_LOCKS.get(delegated[0]) is delegated[1]
                and delegated[1].pid == os.getpid()
            ):
                key = delegated[0]
                delegated[1].depth += 1
                reused = True
    if not reused:
        fd = _acquire_lock_fd(root)
        with _HELD_LOCKS_GUARD:
            _HELD_LOCKS[key] = _HeldLifecycleLock(fd=fd, depth=1)

    token = None
    try:
        if not reused:
            try:
                require_trial_owner(
                    root,
                    trial_owner,
                    reader=_windows_trial_fence_owner if os.name == "nt" else trial_fence_owner,
                )
            except (PathContainmentError, OSError, ValueError) as exc:
                raise LifecycleLockUnavailableError("safe trial ownership is unavailable") from exc
        with _HELD_LOCKS_GUARD:
            held = _HELD_LOCKS[key]
        token = _DELEGATED_LOCKS.set({**(_DELEGATED_LOCKS.get() or {}), str(root): (key, held)})
        yield root
    finally:
        if token is not None:
            _DELEGATED_LOCKS.reset(token)
        _release_lock(key)


@contextmanager
def lifecycle_observation_lock(project_dir: Path) -> Iterator[Path]:
    """Share a stable POSIX project view while excluding lifecycle mutations.

    Observers in different threads/processes can overlap. An active mutation
    still fails admission immediately; a mutation cannot begin during a read.
    Guest runtime observation is Linux-only. Unsupported platforms fail closed
    rather than silently replacing a shared lock with an exclusive one.
    """
    root = canonical_lifecycle_project_root(project_dir)
    fd = _acquire_lock_fd(root, shared=True)
    try:
        yield root
    finally:
        _unlock(fd)
        os.close(fd)


def _acquire_lock_fd(root: Path, *, shared: bool = False) -> int:
    """Open and acquire a new OS lock, closing the descriptor on failure."""

    fd: int | None = None
    try:
        fd = _open_lock_fd(root)
        _try_lock(fd, shared=shared)
    except LifecycleBusyError:
        _close_if_open(fd)
        raise
    except (PathContainmentError, OSError) as exc:
        _close_if_open(fd)
        raise LifecycleLockUnavailableError(
            "safe lifecycle ownership is unavailable"
        ) from exc
    except BaseException:
        _close_if_open(fd)
        raise
    assert fd is not None
    return fd


def _close_if_open(fd: int | None) -> None:
    """Close ``fd`` only when acquisition progressed far enough to open it."""

    if fd is not None:
        os.close(fd)


def _release_lock(key: tuple[str, int]) -> None:
    """Drop one reentrant depth and release the OS lock at depth zero."""

    with _HELD_LOCKS_GUARD:
        entry = _HELD_LOCKS[key]
        entry.depth -= 1
        if entry.depth == 0:
            _unlock(entry.fd)
            os.close(entry.fd)
            del _HELD_LOCKS[key]


def _open_lock_fd(project_dir: Path) -> int:
    """Open the fixed owner-only lock without following a POSIX symlink."""

    if os.name == "nt":
        return _open_windows_lock_fd(project_dir)

    lifecycle_fd = open_dir_contained_nofollow(project_dir, _LIFECYCLE_DIR, create=True)
    try:
        fd = os.open(
            _LOCK_FILE,
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=lifecycle_fd,
        )
    finally:
        os.close(lifecycle_fd)
    os.fchmod(fd, 0o600)
    return fd


def _open_windows_lock_fd(project_dir: Path) -> int:
    """Open the Windows lock component-by-component without following reparses."""

    open_handles: list[int] = []
    lock_handle: int | None = None
    try:
        root_handle = _windows_open_root_handle(project_dir)
        open_handles.append(root_handle)
        _windows_reject_reparse_point(root_handle)

        parent_handle = root_handle
        for component in (".aptl", "lifecycle"):
            child_handle = _windows_open_relative_handle(
                parent_handle, component, directory=True
            )
            open_handles.append(child_handle)
            _windows_reject_reparse_point(child_handle)
            parent_handle = child_handle

        lock_handle = _windows_open_relative_handle(
            parent_handle, _LOCK_FILE, directory=False
        )
        _windows_reject_reparse_point(lock_handle)
        fd = _windows_handle_to_fd(lock_handle)
        # The C runtime descriptor now owns the handle.
        lock_handle = None
    finally:
        if lock_handle is not None:
            _windows_close_handle(lock_handle)
        for handle in reversed(open_handles):
            _windows_close_handle(handle)

    if os.fstat(fd).st_size == 0:
        os.write(fd, b"\0")
    os.lseek(fd, 0, os.SEEK_SET)
    return fd


def _windows_trial_fence_owner(project_dir: Path) -> bytes | None:
    """Read an existing fence through the same no-reparse Windows handles."""
    handles: list[int] = []
    leaf: int | None = None
    try:
        parent = _windows_open_root_handle(project_dir)
        handles.append(parent)
        _windows_reject_reparse_point(parent)
        for component in TRIAL_FENCE.parts[:-1]:
            parent = _windows_open_relative_handle(
                parent, component, directory=True, create=False
            )
            handles.append(parent)
            _windows_reject_reparse_point(parent)
        try:
            leaf = _windows_open_relative_handle(
                parent, TRIAL_FENCE.name, directory=False, create=False
            )
        except FileNotFoundError:
            return None
        _windows_reject_reparse_point(leaf)
        fd = _windows_handle_to_fd(leaf)
        leaf = None
        try:
            return os.read(fd, 65)
        finally:
            os.close(fd)
    finally:
        if leaf is not None:
            _windows_close_handle(leaf)
        for handle in reversed(handles):
            _windows_close_handle(handle)


def _try_lock(fd: int, *, shared: bool = False) -> None:
    """Acquire the platform lock without waiting."""

    try:
        if fcntl is not None:
            mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
            fcntl.flock(fd, mode | fcntl.LOCK_NB)
        elif shared:
            raise OSError("shared lifecycle observations require POSIX flock")
        # Windows uses a one-byte Microsoft C runtime lock.
        elif msvcrt is not None:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        # Fail closed on an unsupported Python runtime.
        else:
            raise OSError("no cross-process file-lock implementation is available")
    except OSError as exc:
        if exc.errno not in (None, errno.EACCES, errno.EAGAIN):
            raise
        raise LifecycleBusyError(
            "another lifecycle owner is active for this project"
        ) from exc


def _unlock(fd: int) -> None:
    """Release the platform lock held on ``fd``."""

    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
    # Windows uses a one-byte Microsoft C runtime lock.
    elif msvcrt is not None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
