"""The RAES consumer inventory names each RAES and env-packs import in src/ (#1556)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "architecture" / "raes-consumer-inventory.md"
UPSTREAM_ROOTS = frozenset(
    {
        "raes",
        "raes_backend_protocols",
        "raes_conformance",
        "raes_contracts",
        "raes_env_packs",
        "raes_operations",
        "raes_processor",
        "raes_runtime",
    }
)
# The name cell of a row for an `import module` statement.
MODULE_IMPORT = "module import"


def _source_imports() -> set[tuple[str, str]]:
    """Return each imported (module, name), at any depth of each file."""

    found: set[tuple[str, str]] = set()
    for path in sorted((ROOT / "src").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_bytes(), filename=str(path))):
            if isinstance(node, ast.Import):
                found.update(
                    (alias.name, MODULE_IMPORT)
                    for alias in node.names
                    if alias.name.split(".")[0] in UPSTREAM_ROOTS
                )
            elif (
                isinstance(node, ast.ImportFrom)
                and node.level == 0
                and node.module is not None
                and node.module.split(".")[0] in UPSTREAM_ROOTS
            ):
                found.update((node.module, alias.name) for alias in node.names)
    return found


def _inventory_rows() -> set[tuple[str, str]]:
    """Return each (module, name) of the name tables of the inventory."""

    text = INVENTORY.read_text(encoding="utf-8")
    section = text.split("\n## Names by capability\n", 1)[1].split("\n## ", 1)[0]
    rows: set[tuple[str, str]] = set()
    for module, names in re.findall(r"^\| `([a-z0-9_.]+)` \| ([^|]+) \|", section, re.MULTILINE):
        cells = re.findall(r"`([^`]+)`", names) or [names.strip()]
        rows.update((module, name) for name in cells)
    return rows


def test_inventory_names_each_upstream_import() -> None:
    missing = _source_imports() - _inventory_rows()
    assert not missing, f"src/ imports names that the inventory does not list: {sorted(missing)}"


def test_inventory_lists_only_imported_names() -> None:
    stale = _inventory_rows() - _source_imports()
    assert not stale, f"the inventory lists names that src/ does not import: {sorted(stale)}"
