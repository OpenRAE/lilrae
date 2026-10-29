"""Typing under ``src`` uses PEP 695 syntax (issue #1326).

SonarCloud runs with ``sonar.python.version=3.12``. It reports python:S6796
on any function typed with a module-level ``TypeVar`` or ``ParamSpec`` and
python:S6794 on a ``TypeAlias`` annotation, and the new-issue gate fails on
the first change to such a module. So no module under ``src`` uses the
legacy constructs: generic helpers carry their own type parameters and type
aliases use the ``type`` statement.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from typing import ParamSpec, TypeAliasType, TypeVar

import pytest
from pydantic import BaseModel

from aptl.appliance.seat.locking import (
    serialized_image_cache,
    serialized_seat_mutation,
)
from aptl.backends.participant_desktop import _bounded
from aptl.utils.strict_json import JsonValue, model_validate_json_strict

_SRC = Path(__file__).resolve().parents[1] / "src"
_LEGACY_TYPING = frozenset({"TypeVar", "ParamSpec", "TypeVarTuple", "TypeAlias"})


def _referenced_name(node: ast.AST) -> str | None:
    """Return the name a ``TypeVar`` or ``typing.TypeVar`` reference uses."""

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _legacy_typing_uses(path: Path) -> list[str]:
    """List each import of or reference to a legacy typing construct."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names = {alias.name for alias in node.names} & _LEGACY_TYPING
            found.extend(f"imports {name}" for name in sorted(names))
        elif (name := _referenced_name(node)) in _LEGACY_TYPING:
            found.append(f"uses {name} at line {node.lineno}")
    return [f"{path.relative_to(_SRC.parent)}: {entry}" for entry in found]


def test_no_module_under_src_uses_legacy_type_variables_or_aliases() -> None:
    modules = sorted(_SRC.rglob("*.py"))
    assert modules, f"no Python modules found under {_SRC}"

    offenders = [entry for path in modules for entry in _legacy_typing_uses(path)]

    assert offenders == []


@pytest.mark.parametrize(
    ("function", "expected"),
    [
        (serialized_seat_mutation, (("P", ParamSpec, None), ("R", TypeVar, None))),
        (serialized_image_cache, (("P", ParamSpec, None), ("R", TypeVar, None))),
        (model_validate_json_strict, (("ModelT", TypeVar, BaseModel),)),
        (_bounded, (("_Item", TypeVar, None),)),
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


def test_json_value_is_a_type_statement_alias() -> None:
    assert type(JsonValue) is TypeAliasType
    assert JsonValue.__name__ == "JsonValue"
    assert JsonValue.__value__ == (
        None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
    )
