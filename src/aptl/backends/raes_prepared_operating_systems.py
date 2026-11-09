"""Complete open node OS identities that the selected scenario adapter knows.

RAES holds a backend to every value it prepares. A node whose OS distribution
and version the author left open is prepared blank, but readback reports the
guest's real identity, so the two differ. An adapter that fixes a node's image
knows that identity before start, and supplies it as
``prepared_operating_systems``: node name to ``(distribution, version)``.
Readback still verifies each value after start.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from raes_contracts.planning import ProvisioningPlan, ProvisionOp, RealizationAuthorityMode

_OS_FIELDS = {"os-distribution": "os_distribution", "os-version": "os_version"}


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


__all__ = ["complete_operating_systems"]
