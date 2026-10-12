"""Generic helpers under ``src`` use PEP 695 type parameters (issue #1326).

SonarCloud runs with ``sonar.python.version=3.12`` and reports python:S6796
on any function typed with a module-level ``TypeVar`` or ``ParamSpec``. The
new-issue gate fails on the first change to such a module, so no module under
``src`` declares one, and the generic helpers carry their own parameters.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from typing import ParamSpec, TypeVar

import pytest
from pydantic import BaseModel

from aptl.appliance.seat.locking import (
    serialized_image_cache,
    serialized_seat_mutation,
)
from aptl.utils.strict_json import model_validate_json_strict

_SRC = Path(__file__).resolve().parents[1] / "src"
_LEGACY_FACTORIES = frozenset({"TypeVar", "ParamSpec", "TypeVarTuple"})


def _factory_name(node: ast.expr) -> str | None:
    """Return the called name for ``TypeVar(...)`` or ``typing.TypeVar(...)``."""

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _legacy_type_variables(path: Path) -> list[str]:
    """List each legacy type-variable import or declaration in one module."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names = {alias.name for alias in node.names} & _LEGACY_FACTORIES
            found.extend(f"imports {name}" for name in sorted(names))
        elif isinstance(node, ast.Call):
            factory = _factory_name(node.func)
            if factory in _LEGACY_FACTORIES:
                found.append(f"calls {factory} at line {node.lineno}")
    return [f"{path.relative_to(_SRC.parent)}: {entry}" for entry in found]


def test_no_module_under_src_declares_a_legacy_type_variable() -> None:
    modules = sorted(_SRC.rglob("*.py"))
    assert modules, f"no Python modules found under {_SRC}"

    offenders = [entry for path in modules for entry in _legacy_type_variables(path)]

    assert offenders == []


@pytest.mark.parametrize(
    ("function", "expected"),
    [
        (serialized_seat_mutation, (("P", ParamSpec, None), ("R", TypeVar, None))),
        (serialized_image_cache, (("P", ParamSpec, None), ("R", TypeVar, None))),
        (model_validate_json_strict, (("ModelT", TypeVar, BaseModel),)),
    ],
    ids=lambda value: getattr(value, "__name__", None),
)
def test_generic_helpers_declare_their_own_type_parameters(
    function: Callable[..., object],
    expected: tuple[tuple[str, type, type | None], ...],
) -> None:
    parameters = function.__type_params__

    assert [
        (parameter.__name__, type(parameter), parameter.__bound__)
        for parameter in parameters
    ] == list(expected)
