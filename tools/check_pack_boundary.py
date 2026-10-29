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

Usage: ``python tools/check_pack_boundary.py [root] [--pack-directory ID=PATH]``
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
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


def owner_declarations() -> dict[str, set[str]]:
    """Return the pack ids that installed out-of-core adapters claim.

    Each provider states the pack it is bound to as ``supported_pack_id``, so
    the owner comes from the adapter itself, not from an entry-point name.
    """

    packs: dict[str, set[str]] = {}
    for distribution in metadata.distributions():
        for entry_point in distribution.entry_points:
            module = entry_point.value.split(":", 1)[0].split(".", 1)[0]
            if not entry_point.group.startswith("aptl.") or module == _CORE_PACKAGE:
                continue
            pack_id = getattr(entry_point.load(), "supported_pack_id", None)
            if isinstance(pack_id, str) and pack_id:
                packs.setdefault(pack_id, set()).add(module)
    return packs


def owner_packs() -> set[str]:
    """Return pack identities declared by installed external provider owners."""
    return set(owner_declarations())


def pack_facts(
    pack_id: str,
    *,
    project_dir: Path | None = None,
    pack_directory: str | None = None,
) -> dict[str, str]:
    """Return ``{fact: kind}`` for what one admitted pack's SDL authors.

    A claimed pack that cannot be admitted raises, so the check fails closed
    instead of passing with no facts to look for.
    """

    from aptl.backends.raes import parse_sdl_file
    from aptl.core.deployment._authored_service_hosts import node_service_hosts
    from aptl.backends._raes_scenario_resolution import resolve_scenario_bundle
    from aptl.core.config import AptlConfig, find_config, load_config

    project_dir = project_dir if project_dir is not None else Path.cwd()
    config_path = find_config(project_dir)
    config = load_config(config_path) if config_path is not None else AptlConfig()
    if (
        pack_directory is not None
        or config.scenario.identity != pack_id
        or config.scenario.source != "env-pack"
    ):
        config = AptlConfig(
            scenario={"identity": pack_id, "pack_directory": pack_directory}
        )

    with tempfile.TemporaryDirectory() as staging:
        bundle = resolve_scenario_bundle(
            project_dir, None, config, staging_root=Path(staging),
        )
        scenario = parse_sdl_file(bundle.sdl_path)
    declarations = owner_declarations().get(pack_id, set())
    facts: dict[str, str] = {
        name: "pack identifier"
        for name in {pack_id, *declarations, *owned_module_identifiers(project_dir, declarations)}
    }
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


def owned_module_identifiers(root: Path, packages: set[str]) -> set[str]:
    """Derive module references from reviewed owner paths, not a denylist."""
    path = root / ".gc/pack-ownership.json"
    if not path.exists():
        return set()
    ledger = json.loads(path.read_text())
    result: set[str] = set()
    for item in ledger.get("owned_paths", ()):
        source, owner = Path(item["path"]), Path(item["owner_path"])
        if (not source.parts or source.parts[0] != "src" or source.suffix != ".py"
                or len(owner.parts) < 2 or owner.parts[0] != "src"
                or ".." in source.parts or ".." in owner.parts):
            raise ValueError("invalid owner path")
        if owner.parts[1] in packages:
            result.add(".".join(source.with_suffix("").parts[1:]))
    return result


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
    exceptions = ownership_exceptions(root)
    results: list[tuple[str, str]] = []
    for path in covered_files(root, patterns):
        relative = str(path.relative_to(root))
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        counts = Counter("sha256:" + hashlib.sha256(line.encode()).hexdigest() for line in lines)
        kinds: set[str] = set()
        for line in lines:
            digest = "sha256:" + hashlib.sha256(line.encode()).hexdigest()
            for fact, kind in lowered.items():
                if kind == "pack identifier" and not relative.startswith("src/aptl/"):
                    continue
                if fact not in line.lower():
                    continue
                accepted = exceptions.get((relative, kind, digest))
                if accepted is None or counts[digest] != accepted:
                    kinds.add(kind)
        kinds = sorted(kinds)
        results.extend((str(path.relative_to(root)), kind) for kind in kinds)
    return results


def ownership_exceptions(root: Path) -> dict[tuple[str, str, str], int]:
    """Accept only reviewed identifier occurrences, never credentials or hosts."""
    path = root / ".gc/pack-ownership.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    if payload.get("schema") != "lilrae-pack-ownership/v1":
        raise ValueError("invalid ownership ledger")
    result = {}
    for item in payload["exceptions"]:
        if (
            item.get("kind") != "pack identifier"
            or type(item.get("count")) is not int or item["count"] < 1
            or not all(isinstance(item.get(key), str) and item[key] for key in
                       ("path", "owner", "symbol", "line_digest", "purpose", "allowed_use", "retirement"))
            or not item["path"].startswith("src/aptl/")
            or ".." in Path(item["path"]).parts
        ):
            raise ValueError("invalid ownership exception")
        key = (item["path"], item["kind"], item["line_digest"])
        if key in result:
            raise ValueError("duplicate ownership exception")
        result[key] = item["count"]
    return result


def main(argv: list[str]) -> int:
    """Print each finding by path and kind; return 1 when any exists."""

    from aptl.core.config import ScenarioSourceConfig
    from aptl.core.scenario_bundle import EnvPackError

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--pack-directory", action="append", default=[], metavar="ID=PATH")
    options = parser.parse_args(argv[1:])
    root = options.root
    facts: dict[str, str] = {}
    try:
        packs = sorted(owner_packs())
    except Exception:
        print("adapter owner discovery failed", file=sys.stderr)
        return 1
    if not packs:
        print("no installed adapter claims a pack; nothing proves the boundary", file=sys.stderr)
        return 1
    try:
        directories: dict[str, str] = {}
        for selection in options.pack_directory:
            pack_id, separator, directory = selection.partition("=")
            if not separator or pack_id in directories or pack_id not in packs:
                raise ValueError("invalid owner source selection")
            ScenarioSourceConfig(identity=pack_id, pack_directory=directory)
            directories[pack_id] = directory
        for pack_id in packs:
            facts.update(
                pack_facts(pack_id, project_dir=root, pack_directory=directories.get(pack_id))
            )
    except Exception:
        print("owner pack acquisition failed; check configured pack sources", file=sys.stderr)
        return 1
    if not facts:
        print("the owner packs author no facts; nothing proves the boundary", file=sys.stderr)
        return 1
    try:
        results = findings(root, facts)
    except (OSError, ValueError, KeyError, TypeError):
        print("invalid ownership ledger", file=sys.stderr)
        return 1
    for path, kind in results:
        print(f"{path}: carries a pack-owned {kind}", file=sys.stderr)
    return 1 if results else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
