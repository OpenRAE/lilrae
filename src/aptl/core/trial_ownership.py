"""Durable exclusion while a RAES trial has unresolved native effects."""

from collections.abc import Callable
from pathlib import Path

from aptl.core.lifecycle_errors import LifecycleBusyError
from aptl.utils.pathsafe import (
    REASON_NOT_FOUND,
    PathContainmentError,
    create_exclusive_nofollow,
    open_contained_nofollow,
)

TRIAL_FENCE = Path(".aptl/lifecycle/trial-owner")


def trial_fence_owner(root: Path) -> bytes | None:
    """Read one bounded private identity; malformed state never means empty."""
    try:
        with open_contained_nofollow(root, TRIAL_FENCE) as source:
            owner = source.read(65)
    except PathContainmentError as exc:
        if exc.reason == REASON_NOT_FOUND:
            return None
        raise
    return owner


def require_trial_owner(
    root: Path,
    owner: bytes | None = None,
    *,
    reader: Callable[[Path], bytes | None] = trial_fence_owner,
) -> None:
    """Refuse unrelated lifecycle work until the admitted runtime reconciles."""
    retained = reader(root)
    if retained is not None and (
        len(retained) != 64 or any(c not in b"0123456789abcdef" for c in retained)
    ):
        raise ValueError("trial ownership state is invalid")
    if retained is not None and retained != owner:
        raise LifecycleBusyError("an unresolved trial owns this placement")


def claim_trial_owner(root: Path, owner: bytes) -> None:
    """Publish a crash-durable fence, or retain the exact existing attempt."""
    require_trial_owner(root, owner)
    if trial_fence_owner(root) is None:
        create_exclusive_nofollow(root, TRIAL_FENCE, owner)
