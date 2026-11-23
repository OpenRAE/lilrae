"""Core holds no TechVault capture implementation (#1700)."""

from __future__ import annotations

import ast
from pathlib import Path


def test_framework_has_no_techvault_capture_implementation_imports() -> None:
    """Core owns the contract and dispatcher, never the first pack's behavior."""

    core = Path(__file__).resolve().parents[2] / "src" / "aptl"
    forbidden_imports: list[str] = []
    for path in core.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: tuple[str, ...] = ()
            if isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = (node.module,)
            if any(module.startswith("aptl_techvault") for module in modules):
                forbidden_imports.append(path.relative_to(core).as_posix())

    assert forbidden_imports == []
    assert not list((core / "core/evidence/adapters").glob("techvault*.py"))
    assert not (core / "core/experiment/capture_registrations.py").exists()
