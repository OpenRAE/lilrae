"""Explicit conversion of historical topology fields in project configuration."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from pydantic import TypeAdapter

from aptl.core.config import AptlConfig
from aptl.core.lifecycle_guard import lifecycle_mutation_lock
from aptl.utils.pathsafe import (
    create_exclusive_nofollow,
    read_contained_nofollow,
    replace_private_nofollow,
)

# Historical schema data, not an adapter vocabulary or runtime default.
_LEGACY_DEFAULTS = {
    "wazuh": True, "victim": True, "kali": True, "reverse": False,
    "enterprise": True, "soc": True, "mail": False, "fileshare": True,
    "dns": True,
}


def migrated_config(data: object, *, scenario_identity: str | None = None) -> dict:
    """Validate conversion without changing the input or choosing a pack."""
    if not isinstance(data, dict):
        raise ValueError("configuration must be an object")
    result = deepcopy(data)
    scenario = result.setdefault("scenario", {})
    if not isinstance(scenario, dict):
        raise ValueError("invalid scenario configuration")
    if scenario_identity is not None:
        if scenario.get("identity") not in (None, scenario_identity):
            raise ValueError("explicit scenario conflicts with existing selection")
        scenario["identity"] = scenario_identity
    if not scenario.get("identity"):
        raise ValueError("migration requires an explicit scenario identity")
    containers = result.get("containers", {})
    if not isinstance(containers, dict):
        raise ValueError("invalid container configuration")
    historical = set(containers) & _LEGACY_DEFAULTS.keys()
    if historical or "profiles" not in containers:
        if set(containers) - _LEGACY_DEFAULTS.keys():
            raise ValueError("unknown or mixed container selection")
        boolean = TypeAdapter(bool)
        flags = {
            name: boolean.validate_python(containers.get(name, default))
            for name, default in _LEGACY_DEFAULTS.items()
        }
        if flags["mail"] or flags["reverse"]:
            raise ValueError("retired profiles require an explicit supported replacement")
        result["containers"] = {
            "profiles": [name for name, enabled in flags.items() if enabled]
        }
    AptlConfig.model_validate(result)
    return result


def migrate_config(path: Path, *, scenario_identity: str | None = None) -> bool:
    """Write a validated conversion once, preserving original bytes beside it."""
    with lifecycle_mutation_lock(path.parent):
        return _migrate_locked(path, scenario_identity=scenario_identity)


def _migrate_locked(path: Path, *, scenario_identity: str | None) -> bool:
    """Keep the lifecycle owner lock through reading and atomic replacement."""
    original = read_contained_nofollow(path.parent, path.name)
    try:
        data = json.loads(original)
    except (ValueError, UnicodeError):
        raise ValueError("invalid configuration JSON") from None
    converted = migrated_config(data, scenario_identity=scenario_identity)
    if converted == data:
        return False
    backup = path.name + ".bak"
    try:
        create_exclusive_nofollow(path.parent, backup, original)
    except FileExistsError:
        if read_contained_nofollow(path.parent, backup) != original:
            raise ValueError("configuration backup already exists with different content") from None
    # Refuse a concurrent edit instead of replacing it with a stale conversion.
    if read_contained_nofollow(path.parent, path.name) != original:
        raise ValueError("configuration changed during migration")
    payload = (json.dumps(converted, indent=4) + "\n").encode()
    replace_private_nofollow(path.parent, path.name, payload)
    return True
