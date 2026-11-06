"""Trial-bound Wazuh agent ids retained across capture-source reconstruction.

Core creates one record for each admitted trial during that trial's first
provisioning capture. Only that capture may add ids; every later context only
reads. A record that is missing after provisioning is lost evidence, so a
post-restart observation can never become the baseline it is compared with.
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
    return (json.dumps(dict(ids), sort_keys=True) + "\n").encode()


def trial_enrollment_retainer(
    project_dir: Path, trial_key: str, *, establish: bool
) -> EnrollmentRetainer:
    """Return the trial's retainer; only the establishing capture may write.

    With ``establish``, core creates the trial's record once. When the record
    already exists, this context is read-only, like every other context.
    The retainer returns the ids retained before the call. A writable retainer
    then adds hosts it has not retained; it never replaces a retained id.
    """

    match = _TRIAL_KEY.fullmatch(trial_key)
    if match is None:
        raise ValueError("enrollment-trial-key-invalid")
    relpath = WAZUH_TRIAL_ENROLLMENT_DIR / f"{match.group(1)}.json"
    writable = False
    if establish:
        try:
            create_exclusive_nofollow(project_dir, relpath, _encode({}))
            writable = True
        except (OSError, PathContainmentError):
            writable = False

    def retain(observed: Mapping[str, str]) -> dict[str, str] | None:
        if not _valid_ids(observed):
            return None
        prior = _read(project_dir, relpath)
        if prior is None or not writable:
            return prior
        merged = {**dict(observed), **prior}
        if merged != prior:
            if not _valid_ids(merged):
                return None
            try:
                replace_private_nofollow(project_dir, relpath, _encode(merged))
            except (OSError, ValueError, PathContainmentError):
                return None
        return prior

    return retain


__all__ = ("EnrollmentRetainer", "trial_enrollment_retainer")
