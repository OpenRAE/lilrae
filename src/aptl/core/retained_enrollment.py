"""Trial-bound Wazuh agent ids retained across capture-source reconstruction.

Core creates one record for each admitted trial during that trial's first
provisioning capture. A create-once marker beside the record proves that the
trial was established. Only the establishing capture may add ids; every later
context only reads. A record that is missing after establishment is lost
evidence, so a post-restart observation can never become its own baseline.
The explicit volume reset clears the records through the existing
``clear-wazuh-enrollment-baseline`` cleanup action.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path

from aptl.core.lifecycle_cleanup import WAZUH_TRIAL_ENROLLMENT_DIR
from aptl.utils.pathsafe import (
    PathContainmentError,
    create_exclusive_nofollow,
    open_contained_nofollow,
    replace_private_nofollow,
)

_TRIAL_KEY = re.compile(r"sha256:([0-9a-f]{64})")
_NODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_AGENT_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_MAX_NODES = 256
_MAX_BYTES = 64 * 1024

EnrollmentRetainer = Callable[[Mapping[str, str]], dict[str, str] | None]


def _valid_ids(value: object) -> bool:
    """Accept a bounded node-to-id map with no duplicate agent ids."""

    return (
        isinstance(value, Mapping)
        and len(value) <= _MAX_NODES
        and all(
            isinstance(node, str)
            and _NODE.fullmatch(node) is not None
            and isinstance(agent_id, str)
            and _AGENT_ID.fullmatch(agent_id) is not None
            for node, agent_id in value.items()
        )
        and len(set(value.values())) == len(value)
    )


def _read(project_dir: Path, relpath: Path) -> dict[str, str] | None:
    """Return the trial's retained ids, or ``None`` when missing or invalid."""

    try:
        with open_contained_nofollow(project_dir, relpath) as handle:
            raw = handle.read(_MAX_BYTES + 1)
        recorded = None if len(raw) > _MAX_BYTES else json.loads(raw)
    except (OSError, ValueError, PathContainmentError):
        return None
    return dict(recorded) if _valid_ids(recorded) else None


def _encode(ids: Mapping[str, str]) -> bytes:
    """Return the canonical record bytes."""

    return (json.dumps(dict(ids), sort_keys=True) + "\n").encode()


def _establish(project_dir: Path, relpath: Path) -> bool:
    """Create the trial's marker and empty record once; return whether this did."""

    try:
        marker = relpath.with_suffix(".established")
        create_exclusive_nofollow(project_dir, marker, b"")
        create_exclusive_nofollow(project_dir, relpath, _encode({}))
    except (OSError, PathContainmentError):
        return False
    return True


def _add_new_hosts(
    project_dir: Path,
    relpath: Path,
    prior: dict[str, str],
    observed: Mapping[str, str],
) -> bool:
    """Retain hosts not yet retained, never replacing an id; return success."""

    merged = {**dict(observed), **prior}
    if merged == prior:
        return True
    try:
        if not _valid_ids(merged):
            raise ValueError("enrollment-ids-invalid")
        replace_private_nofollow(project_dir, relpath, _encode(merged))
    except (OSError, ValueError, PathContainmentError):
        return False
    return True


def trial_enrollment_retainer(
    project_dir: Path, trial_key: str, *, establish: bool
) -> EnrollmentRetainer:
    """Return the trial's retainer; only the establishing capture may write.

    With ``establish``, core creates the trial's record once. When the trial
    was already established, this context is read-only, like every other one.
    The retainer returns the ids retained before the call. A writable retainer
    then adds hosts it has not retained; it never replaces a retained id.
    """

    match = _TRIAL_KEY.fullmatch(trial_key)
    if match is None:
        raise ValueError("enrollment-trial-key-invalid")
    relpath = WAZUH_TRIAL_ENROLLMENT_DIR / f"{match.group(1)}.json"
    writable = establish and _establish(project_dir, relpath)

    def retain(observed: Mapping[str, str]) -> dict[str, str] | None:
        """Return the ids retained before this call, or ``None`` if unproven."""

        prior = _read(project_dir, relpath) if _valid_ids(observed) else None
        if prior is not None and writable:
            if not _add_new_hosts(project_dir, relpath, prior, observed):
                prior = None
        return prior

    return retain


__all__ = ("EnrollmentRetainer", "trial_enrollment_retainer")
