"""Bounded native queries shared by the TechVault product readers."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Protocol, cast

from aptl.core.deployment.errors import BackendTimeoutError


class ReadbackBackend(Protocol):
    """The existing container command boundary available to an adapter."""

    def container_exec(
        self, name: str, cmd: list[str], *, timeout: int | None = None
    ) -> object: ...


class ReadbackUnavailable(ValueError):
    """Native state did not establish the requested managed value."""


def output(backend: ReadbackBackend, container: str, argv: list[str]) -> str:
    """Read successful bounded output without exposing failure contents."""

    try:
        result = backend.container_exec(container, argv, timeout=30)
    except (BackendTimeoutError, OSError) as exc:
        raise ReadbackUnavailable("native-readback-unavailable") from exc
    text = getattr(result, "stdout", None)
    if (
        getattr(result, "returncode", 1) != 0
        or not isinstance(text, str)
        or len(text.encode()) > 2 * 1024 * 1024
    ):
        raise ReadbackUnavailable("native-readback-unavailable")
    return text.strip()


def json_output(backend: ReadbackBackend, container: str, argv: list[str]) -> object:
    """Decode one native response, rejecting malformed or oversized data."""

    try:
        return json.loads(output(backend, container, argv))
    except (ValueError, RecursionError) as exc:
        raise ReadbackUnavailable("native-readback-invalid") from exc


def identifier(value: str) -> str:
    """Admit SQL identifiers before they enter a native query."""

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ReadbackUnavailable("native-identifier-unsupported")
    return value


def value(item: object) -> str:
    """Normalize the owner's enum vocabulary."""

    return str(getattr(item, "value", item) or "")


def require(condition: object) -> None:
    """Withhold a concern when any required native fact is unproven."""

    if not condition:
        raise ReadbackUnavailable("native-fact-unobserved")


def version_matches(requested: str, actual: str) -> bool:
    """Keep an authored major or minor version within its native release family."""

    return bool(actual) and (
        not requested or actual == requested or actual.startswith(requested + ".")
    )


def as_mapping(item: object) -> Mapping[str, object]:
    """Require a native object without accepting an empty fallback."""

    require(isinstance(item, Mapping))
    return cast(Mapping[str, object], item)


def observed_version(requested: str, actual: str) -> str:
    """Report a native version at the precision of an authored release family."""

    require(version_matches(requested, actual))
    return (
        ".".join(actual.split(".")[: len(requested.split("."))])
        if requested
        else actual
    )
