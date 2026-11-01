"""The RAES consumer inventory names each RAES and env-packs use in src/ (#1556)."""

from __future__ import annotations

import ast
import importlib.util
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


def _is_module(name: str) -> bool:
    # find_spec imports the parent packages, which are installed RAES
    # distributions; it does not import product code.
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        # The parent is a module, not a package, so the name is an attribute.
        return False


def _module_bindings(tree: ast.Module) -> dict[str, str]:
    """Map each local name that holds an upstream module to that module."""

    bound: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in UPSTREAM_ROOTS:
                    local = alias.asname or alias.name.split(".")[0]
                    bound[local] = alias.name if alias.asname else local
        elif isinstance(node, ast.ImportFrom) and _upstream_from(node):
            for alias in node.names:
                if _is_module(f"{node.module}.{alias.name}"):
                    bound[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return bound


def _upstream_from(node: ast.ImportFrom) -> bool:
    return node.level == 0 and node.module is not None and node.module.split(".")[0] in UPSTREAM_ROOTS


def _attribute_reads(tree: ast.Module, bound: dict[str, str]) -> set[tuple[str, str]]:
    """Return each (module, attribute) that the file reads through a module name."""

    reads: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        chain: list[str] = []
        current: ast.expr = node
        while isinstance(current, ast.Attribute):
            chain.insert(0, current.attr)
            current = current.value
        if not isinstance(current, ast.Name) or current.id not in bound:
            continue
        module = bound[current.id]
        for attribute in chain:
            if not _is_module(f"{module}.{attribute}"):
                reads.add((module, attribute))
                break
            module = f"{module}.{attribute}"
    return reads


def _source_uses() -> set[tuple[str, str]]:
    """Return each imported (module, name) and each attribute read through a module."""

    uses: set[tuple[str, str]] = set()
    for path in sorted((ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_bytes(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                uses.update(
                    (alias.name, MODULE_IMPORT)
                    for alias in node.names
                    if alias.name.split(".")[0] in UPSTREAM_ROOTS
                )
            elif isinstance(node, ast.ImportFrom) and _upstream_from(node):
                uses.update((node.module, alias.name) for alias in node.names)
        uses |= _attribute_reads(tree, _module_bindings(tree))
    return uses


def _inventory_rows() -> set[tuple[str, str]]:
    """Return each (module, name) of the name tables of the inventory."""

    text = INVENTORY.read_text(encoding="utf-8")
    section = text.split("\n## Names by capability\n", 1)[1].split("\n## ", 1)[0]
    rows: set[tuple[str, str]] = set()
    for module, names in re.findall(r"^\| `([a-z0-9_.]+)` \| ([^|]+) \|", section, re.MULTILINE):
        rows.update((module, name.strip().strip("`")) for name in names.split(","))
    return rows


def test_inventory_names_each_upstream_use() -> None:
    missing = _source_uses() - _inventory_rows()
    assert not missing, f"src/ uses names that the inventory does not list: {sorted(missing)}"


def test_inventory_lists_only_used_names() -> None:
    stale = _inventory_rows() - _source_uses()
    assert not stale, f"the inventory lists names that src/ does not use: {sorted(stale)}"
