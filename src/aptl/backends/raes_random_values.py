"""Realize ``random_value`` generated artifacts as the text of their consumers.

LilRAE generates each value once per run and keeps it beside the scenario
bundle, so every interpretation of the run's plan uses the same value. A
consuming content placement receives the value as inline text. Readback
reads each stored value and checks it against its declared generator.
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
from raes_processor.semantics.realization import CONCERN_PAYLOAD_PATH

from aptl.backends._raes_observation_helpers import ObservedResource

_ALPHABETS = {
    "hex_lower": "0123456789abcdef",
    "hex_upper": "0123456789ABCDEF",
    "alphanumeric": "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
}
_ROOT = ".lilrae-generated-values"
_MAX_LENGTH = 4096


def _generator(spec: Mapping[str, Any]) -> tuple[str, int, str, str]:
    parameters = spec.get("random_value") or {}
    alphabet = _ALPHABETS.get(parameters.get("alphabet", ""))
    length = parameters.get("length")
    if alphabet is None or type(length) is not int or not 1 <= length <= _MAX_LENGTH:
        raise ValueError("random value parameters are unsupported")
    form = parameters.get("format") or {}
    return alphabet, length, str(form.get("prefix", "")), str(form.get("suffix", ""))


def _value(spec: Mapping[str, Any]) -> str:
    alphabet, length, prefix, suffix = _generator(spec)
    return prefix + "".join(secrets.choice(alphabet) for _ in range(length)) + suffix


def _conforms(value: str, spec: Mapping[str, Any]) -> bool:
    alphabet, length, prefix, suffix = _generator(spec)
    body = value[len(prefix) : len(value) - len(suffix)]
    return (
        len(value) == len(prefix) + length + len(suffix)
        and value.startswith(prefix)
        and value.endswith(suffix)
        and set(body) <= set(alphabet)
    )


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


def _value_paths(payload: Mapping[str, Any], root: Path) -> dict[tuple[str, str], Path]:
    """Return ``(artifact name, output) -> stored value path`` for one artifact."""
    name = str(payload.get("name", ""))
    run = hashlib.sha256(str(payload.get("scope_binding", "")).encode()).hexdigest()[:24]
    return {
        (name, str(output.get("name", ""))): root
        / _ROOT
        / run
        / hashlib.sha256(f"{name}/{output.get('name', '')}".encode()).hexdigest()
        for output in payload["spec"].get("outputs") or ()
    }


def random_values(
    resources: Sequence[PlannedResource], root: Path
) -> dict[tuple[str, str], str]:
    """Return ``(artifact name, output) -> value`` for every random-value artifact."""
    values = {}
    for resource in resources:
        if is_random_value(resource):
            spec = resource.payload["spec"]
            for key, path in _value_paths(resource.payload, root).items():
                values[key] = _create_once(path, spec)
    return values


def observe_random_value(resource: PlannedResource, root: Path) -> ObservedResource:
    """Read back each stored value; realized only when every one fits its generator."""
    spec = resource.payload["spec"]
    paths = _value_paths(resource.payload, root)
    try:
        realized = bool(paths) and all(
            path.is_file() and not path.is_symlink() and _conforms(path.read_text(encoding="utf-8"), spec)
            for path in paths.values()
        )
    except (OSError, ValueError):
        realized = False
    if not realized:
        return ObservedResource(realized=False)
    return ObservedResource(
        realized=True, concerns={CONCERN_PAYLOAD_PATH["generated-artifact"]: dict(spec)}
    )


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
