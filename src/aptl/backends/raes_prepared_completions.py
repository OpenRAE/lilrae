"""Commit, before start, the open values that LilRAE will deliver.

RAES holds a backend to every value it prepares. LilRAE prepares a plan
unchanged, so an open field stays blank while readback reports the value that
LilRAE realized. Two sources know those values before start:

- An adapter whose images fix a node's OS supplies ``prepared_operating_systems``:
  node name to ``(distribution, version)``.
- LilRAE's own backend implementation profiles select runtime values, such as
  environment variables or an entrypoint, from the plan.

Each value is prepared in the form that readback reports. Readback still
verifies every value after start.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from typing import Any

from raes_contracts.planning import ProvisioningPlan, ProvisionOp, RealizationAuthorityMode
from raes_processor.semantics.realization import CONCERN_PAYLOAD_PATH

from aptl.backends._raes_runtime_environment_observation import declared_disclosure
from aptl.backends.raes_realization_model import AptlRealization

_OS_FIELDS = {"os-distribution": "os_distribution", "os-version": "os_version"}
_RUNTIME_PREFIX = ("spec", "node", "runtime")


def _open_kinds(request: ProvisioningPlan) -> dict[str, set[str]]:
    kinds: dict[str, set[str]] = {}
    for authority in request.realization_authority:
        if authority.mode is RealizationAuthorityMode.OPEN:
            kinds.setdefault(authority.address, set()).add(authority.requirement_kind)
    return kinds


def complete_operating_systems(
    request: ProvisioningPlan,
    operations: dict[str, ProvisionOp],
    known: Mapping[str, tuple[str, str]],
) -> None:
    """Fill each blank open OS field from ``known``; leave every other value."""
    open_kinds = _open_kinds(request)
    for address, operation in operations.items():
        payload = operation.payload
        identity = known.get(payload.get("name", "")) if operation.resource_type == "node" else None
        if identity is None:
            continue
        values = dict(zip(("os_distribution", "os_version"), identity, strict=True))
        completed = {
            field: values[field]
            for kind, field in _OS_FIELDS.items()
            if kind in open_kinds.get(address, ()) and not payload.get(field)
        }
        if completed:
            operations[address] = replace(operation, payload={**payload, **completed})


def _selected_value(kind: str, runtime: Any) -> object | None:
    """Return one selected runtime value in the form that readback reports."""
    if kind == "runtime-environment":
        return declared_disclosure(runtime)
    value: object = runtime.model_dump(mode="json", by_alias=True, exclude_none=True)
    for token in CONCERN_PAYLOAD_PATH[kind][len(_RUNTIME_PREFIX) :]:
        value = value.get(token) if isinstance(value, dict) else None
    return value


def _get(payload: Mapping[str, Any], path: tuple[str, ...]) -> object | None:
    value: object = payload
    for token in path:
        value = value.get(token) if isinstance(value, Mapping) else None
    return value


def complete_backend_selections(
    request: ProvisioningPlan,
    operations: dict[str, ProvisionOp],
    realization: AptlRealization,
) -> None:
    """Fill each blank open runtime value that a backend profile selected."""
    open_kinds = _open_kinds(request)
    for node in realization.nodes:
        operation = operations.get(node.address)
        if operation is None or node.runtime is None:
            continue
        payload = None
        for kind in node.backend_selected_concerns:
            path = CONCERN_PAYLOAD_PATH.get(kind)
            if (
                path is None
                or path[: len(_RUNTIME_PREFIX)] != _RUNTIME_PREFIX
                or kind not in open_kinds.get(node.address, ())
                or _get(operation.payload, path) not in (None, [], {})
            ):
                continue
            value = _selected_value(kind, node.runtime)
            if value is None:
                continue
            payload = payload or deepcopy(operation.payload)
            target = payload
            for token in path[:-1]:
                if not isinstance(target.get(token), dict):
                    target[token] = {}
                target = target[token]
            target[path[-1]] = value
        if payload is not None:
            operations[node.address] = replace(operation, payload=payload)


__all__ = ["complete_backend_selections", "complete_operating_systems"]
