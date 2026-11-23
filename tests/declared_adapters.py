"""The scenario adapters this distribution declares, read from its build metadata.

Generic boundary tests prove that core runs, builds and imports without an
adapter. They derive the adapters from the ``aptl.*`` entry points in
``pyproject.toml`` rather than naming one, so another adapter needs no test
edit (#1700). Import-safe: it reads only ``pyproject.toml``.

Named without a ``test_`` prefix so pytest does not collect it.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CORE_PACKAGE = "aptl"


def _entry_points() -> dict[str, dict[str, str]]:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return {
        group: entries
        for group, entries in project["project"].get("entry-points", {}).items()
        if group.startswith("aptl.")
    }


def adapter_packages() -> frozenset[str]:
    """Return the top-level packages that provide out-of-core ``aptl.*`` entry points."""

    packages = {
        value.split(":", 1)[0].split(".", 1)[0]
        for entries in _entry_points().values()
        for value in entries.values()
    }
    return frozenset(packages - {_CORE_PACKAGE})


__all__ = ["PROJECT_ROOT", "adapter_packages"]
