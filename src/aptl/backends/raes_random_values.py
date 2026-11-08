"""Realize ``random_value`` generated artifacts as the text of their consumers.

LilRAE generates each value once per run and keeps it under the scenario
bundle, so every interpretation of the run's plan uses the same value. A
consuming content placement receives the value as inline text.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from raes_contracts.planning import PlannedResource

_ALPHABETS = {
    "hex_lower": "0123456789abcdef",
    "hex_upper": "0123456789ABCDEF",
    "alphanumeric": "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
}
_ROOT = ".lilrae-generated-values"
_MAX_LENGTH = 4096


def _value(spec: Mapping[str, Any]) -> str:
    parameters = spec.get("random_value") or {}
    alphabet = _ALPHABETS.get(parameters.get("alphabet", ""))
    length = parameters.get("length")
    if alphabet is None or type(length) is not int or not 1 <= length <= _MAX_LENGTH:
        raise ValueError("random value parameters are unsupported")
    form = parameters.get("format") or {}
    body = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"{form.get('prefix', '')}{body}{form.get('suffix', '')}"


def _create_once(path: Path, spec: Mapping[str, Any]) -> str:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        return path.read_text(encoding="utf-8")
    value = _value(spec)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(value)
    return value


def is_random_value(resource: PlannedResource) -> bool:
    spec = resource.payload.get("spec") if isinstance(resource.payload, Mapping) else None
    return isinstance(spec, Mapping) and spec.get("generator") == "random_value"


def random_values(
    resources: Sequence[PlannedResource], root: Path
) -> dict[tuple[str, str], str]:
    """Return ``(artifact name, output) -> value`` for every random-value artifact."""
    values = {}
    for resource in resources:
        if not is_random_value(resource):
            continue
        payload = resource.payload
        spec = payload.get("spec")
        name = str(payload.get("name", ""))
        run = hashlib.sha256(str(payload.get("scope_binding", "")).encode()).hexdigest()[:24]
        for output in spec.get("outputs") or ():
            output_name = str(output.get("name", ""))
            path = root / _ROOT / run / hashlib.sha256(f"{name}/{output_name}".encode()).hexdigest()
            values[(name, output_name)] = _create_once(path, spec)
    return values


def inline_random_values(
    resources: Sequence[PlannedResource], values: Mapping[tuple[str, str], str]
) -> list[PlannedResource]:
    """Give each content placement that reads a random value that value as text."""
    result = []
    for resource in resources:
        payload = resource.payload
        spec = payload.get("spec") if isinstance(payload, Mapping) else None
        source = spec.get("text_from") if isinstance(spec, Mapping) else None
        key = (
            (str(source.get("generated_artifact", "")), str(source.get("output", "")))
            if isinstance(source, Mapping)
            else None
        )
        if key in values:
            spec = {**spec, "text": values[key], "text_from": None}
            resource = replace(resource, payload={**payload, "spec": spec})
        result.append(resource)
    return result
