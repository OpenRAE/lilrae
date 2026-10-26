"""TechVault retained per-host enrollment identity readiness is compared against.

Comparing the manager's current view of an agent with that agent's current
`client.keys` proves only that the two agree right now. Delete the retained
identity, let the agent re-enroll, and both sides move together to a new id --
the comparison still passes while every event attributed to the old id has been
orphaned. That is precisely the failure the released scope calls out, so the
comparison needs an identity recorded *before* the restart to compare against.

This module records and reads that baseline. The first successful observation
of a host records its id; every later observation compares against the recorded
one. The baseline is APTL-owned realization state beside the other
backend-owned state, so it survives the container lifecycle it is there to
observe. The explicit volume reset that legitimately clears enrollment clears
it too, through the APTL lifecycle cleanup action that every lab start records
(:mod:`aptl.core.lifecycle_cleanup`), independent of which adapter is installed.
"""

from __future__ import annotations

import json
from pathlib import Path

from aptl.utils.pathsafe import (
    read_contained_nofollow,
    replace_private_nofollow,
    PathContainmentError,
    REASON_NOT_FOUND,
)
from aptl.core.lifecycle_cleanup import WAZUH_ENROLLMENT_BASELINE_RELPATH

ENROLLMENT_BASELINE_RELPATH = WAZUH_ENROLLMENT_BASELINE_RELPATH


def enrollment_baseline(scenario_root: Path) -> dict[str, str] | None:
    """Return the baseline, empty when absent and ``None`` when unreadable."""

    result: dict[str, str] | None = None
    try:
        recorded = json.loads(
            read_contained_nofollow(scenario_root, ENROLLMENT_BASELINE_RELPATH)
        )
    except PathContainmentError as exc:
        if exc.reason == REASON_NOT_FOUND:
            result = {}
    except (OSError, ValueError):
        pass
    else:
        if _valid_baseline(recorded):
            result = dict(recorded)
    return result


def _valid_baseline(recorded: object) -> bool:
    """Return whether the decoded baseline is a non-empty string mapping."""

    return isinstance(recorded, dict) and all(
        isinstance(node, str)
        and bool(node)
        and isinstance(identifier, str)
        and bool(identifier)
        for node, identifier in recorded.items()
    )


def record_enrollment_baseline(scenario_root: Path, observed: dict[str, str]) -> bool:
    """Record ids for hosts not yet baselined, never overwriting an existing one.

    An existing entry is deliberately immutable here: overwriting it would erase
    the very evidence a later comparison depends on, turning a lost identity
    into a fresh baseline that passes. The explicit volume reset is the one
    operation that clears it, through
    :func:`aptl.core.lifecycle_cleanup.clear_wazuh_enrollment_baseline`.
    """

    recorded = enrollment_baseline(scenario_root)
    if recorded is None:
        return False
    merged = {**{k: v for k, v in observed.items() if k and v}}
    merged.update(recorded)
    try:
        replace_private_nofollow(
            scenario_root,
            ENROLLMENT_BASELINE_RELPATH,
            (json.dumps(merged, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        )
    except (OSError, ValueError, PathContainmentError):
        # A baseline that cannot be written must not be treated as satisfied;
        # the caller sees no recorded identity and reports enrollment unproven.
        return False
    return enrollment_baseline(scenario_root) == merged


__all__ = (
    "ENROLLMENT_BASELINE_RELPATH",
    "enrollment_baseline",
    "record_enrollment_baseline",
)
