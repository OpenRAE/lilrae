"""Regression gates for the hard RAES Python namespace cutover."""

from __future__ import annotations

import ast
import csv
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
LEGACY_IMPORT_ROOTS = frozenset(
    {
        "aces_backend_protocols",
        "aces_conformance",
        "aces_contracts",
        "aces_operations",
        "aces_processor",
        "aces_runtime",
        "aces_sdl",
    }
)
REMOVED_RAES_BACKEND_ROOTS = frozenset(
    {
        "raes_backend_libvirt",
        "raes_reference_backend",
    }
)
IDENTITY_LEDGER = (
    PROJECT_ROOT
    / "docs"
    / "reviews"
    / "962-lilrae-readiness"
    / "identity-disposition.tsv"
)
KNOWN_PRIVATE_RAES_IMPORTS: set[tuple[str, str, str]] = set()


def test_project_does_not_depend_on_removed_aces_distribution() -> None:
    """The application no longer depends on the retired distribution."""

    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())

    assert all(
        not dependency.startswith("aces-sdl")
        for dependency in project["project"]["dependencies"]
    )


def _source_and_test_imports_of(import_roots: frozenset[str]) -> list[str]:
    """Return ``path:line:roots`` for every source or test import of the roots."""

    offenders: list[str] = []
    for root in (PROJECT_ROOT / "src", PROJECT_ROOT / "tests"):
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = {alias.name.split(".", 1)[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported = {node.module.split(".", 1)[0]}
                else:
                    continue
                matched = sorted(imported & import_roots)
                if matched:
                    offenders.append(
                        f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}:"
                        + ",".join(matched)
                    )
    return offenders


def test_runtime_and_tests_do_not_import_removed_aces_packages() -> None:
    """RAES 3.1 ships no compatibility aliases for the old Python packages."""

    assert _source_and_test_imports_of(LEGACY_IMPORT_ROOTS) == []


def test_runtime_and_tests_do_not_import_raes_concrete_backends() -> None:
    """The release after RAES 7.0.0 removes its concrete backends (#1406)."""

    assert _source_and_test_imports_of(REMOVED_RAES_BACKEND_ROOTS) == []


def test_no_private_raes_imports_or_manifest_fallback_remain() -> None:
    """Production source uses the public contracts in the pinned RAES release."""

    observed: set[tuple[str, str, str]] = set()
    source_root = PROJECT_ROOT / "src"
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if not node.module.startswith(("raes.", "raes_")):
                continue
            if "._" not in node.module and not any(
                alias.name.startswith("_") for alias in node.names
            ):
                continue
            observed.update(
                (
                    str(path.relative_to(PROJECT_ROOT)),
                    node.module,
                    alias.name,
                )
                for alias in node.names
            )

    assert observed == KNOWN_PRIVATE_RAES_IMPORTS

    with IDENTITY_LEDGER.open(newline="", encoding="utf-8") as stream:
        rows = {
            row["surface_id"]: row for row in csv.DictReader(stream, delimiter="\t")
        }

    assert all(
        not surface_id.startswith("raes-private-") for surface_id in rows
    )

    manifest = (
        PROJECT_ROOT / "src" / "aptl" / "backends" / "raes_manifest.py"
    ).read_text()
    assert (
        "from raes_contracts.manifest_authority import BACKEND_SUPPORTED_CONTRACT_IDS"
        in manifest
    )
    assert "except ImportError:" not in manifest
