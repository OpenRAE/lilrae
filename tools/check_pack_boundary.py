#!/usr/bin/env python3
"""Fail when generic LilRAE files carry an adapter-owned pack fact (#1121, #1273).

The facts a scenario pack owns stay in its SDL or its adapter. This check finds
the owners and their facts without a fixed string list:

* an owner is a pack an installed adapter claims: any ``aptl.*`` entry point
  whose provider lives outside the ``aptl`` package names its pack;
* the facts are what that pack's admitted SDL authors: canonical service
  hostnames, DNS zones, ``secret_fixture`` credential values, and mail-shaped
  account usernames.

It scans the generic paths in :data:`COVERED` and reports each match by path
and fact kind, never by value. #1273 covers the participant desktop, the rule
tools, and the account providers, including the generic core directory.

Usage: ``python tools/check_pack_boundary.py [<repository root>]``
"""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Iterable, Mapping
from importlib import metadata
from pathlib import Path

#: Generic paths that must carry no pack fact. Globs are repository-relative.
COVERED = (
    "scripts/**/*",
    "appliance/guest/**/*",
    "mcp/*/docker-lab-config.json",
    "src/aptl/**/*",
)
_CORE_PACKAGE = "aptl"
_MIN_SECRET_LENGTH = 6


def owner_packs() -> set[str]:
    """Return the pack ids that installed out-of-core adapters claim.

    Each provider states the pack it is bound to as ``supported_pack_id``, so
    the owner comes from the adapter itself, not from an entry-point name.
    """

    packs: set[str] = set()
    for distribution in metadata.distributions():
        for entry_point in distribution.entry_points:
            module = entry_point.value.split(":", 1)[0].split(".", 1)[0]
            if not entry_point.group.startswith("aptl.") or module == _CORE_PACKAGE:
                continue
            pack_id = getattr(entry_point.load(), "supported_pack_id", None)
            if isinstance(pack_id, str) and pack_id:
                packs.add(pack_id)
    return packs


def pack_facts(pack_id: str) -> dict[str, str]:
    """Return ``{fact: kind}`` for what one admitted pack's SDL authors.

    A claimed pack that cannot be admitted raises, so the check fails closed
    instead of passing with no facts to look for.
    """

    from aptl.backends.raes import parse_sdl_file
    from aptl.core.deployment._authored_service_hosts import node_service_hosts
    from aptl.core.scenario_bundle import env_pack_bundle

    with tempfile.TemporaryDirectory() as staging:
        bundle = env_pack_bundle(Path(staging), pack_id)
        scenario = parse_sdl_file(bundle.sdl_path)
    facts: dict[str, str] = {}
    for node in scenario.nodes.values():
        runtime = getattr(node, "runtime", None)
        facts.update({host: "hostname" for host in node_service_hosts(runtime)})
        for service in getattr(runtime, "dns_services", None) or ():
            for zone in getattr(service, "zones", None) or ():
                facts[str(zone.name)] = "hostname"
    for account in scenario.accounts.values():
        if "@" in account.username:
            facts[account.username] = "account username"
        for binding in account.credential_bindings or ():
            value = getattr(binding.material, "value", None)
            if isinstance(value, str) and len(value) >= _MIN_SECRET_LENGTH:
                facts[value] = "credential"
    return facts


def covered_files(root: Path, patterns: Iterable[str] = COVERED) -> list[Path]:
    """Return the regular files the covered globs name."""

    found = {path for pattern in patterns for path in root.glob(pattern)}
    return sorted(
        path for path in found
        if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts
    )


def findings(
    root: Path, facts: Mapping[str, str], patterns: Iterable[str] = COVERED
) -> list[tuple[str, str]]:
    """Return ``(relative path, fact kind)`` for each covered file with a fact."""

    lowered = {fact.lower(): kind for fact, kind in facts.items()}
    results: list[tuple[str, str]] = []
    for path in covered_files(root, patterns):
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        kinds = sorted({kind for fact, kind in lowered.items() if fact in text})
        results.extend((str(path.relative_to(root)), kind) for kind in kinds)
    return results


def main(argv: list[str]) -> int:
    """Print each finding by path and kind; return 1 when any exists."""

    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1]
    facts: dict[str, str] = {}
    packs = sorted(owner_packs())
    if not packs:
        print("no installed adapter claims a pack; nothing proves the boundary", file=sys.stderr)
        return 1
    for pack_id in packs:
        facts.update(pack_facts(pack_id))
    if not facts:
        print("the owner packs author no facts; nothing proves the boundary", file=sys.stderr)
        return 1
    results = findings(root, facts)
    for path, kind in results:
        print(f"{path}: carries a pack-owned {kind}", file=sys.stderr)
    return 1 if results else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
