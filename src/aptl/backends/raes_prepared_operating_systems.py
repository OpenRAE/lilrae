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

_OPEN_FIELDS = {"os-distribution": "os_distribution", "os-version": "os_version"}


def complete_operating_systems(
    request: ProvisioningPlan,
    operations: dict[str, ProvisionOp],
    known: Mapping[str, tuple[str, str]],
) -> None:
    """Fill each blank open OS field from ``known``; leave every other value."""
    open_fields: dict[str, set[str]] = {}
    for authority in request.realization_authority:
        if authority.mode is RealizationAuthorityMode.OPEN and authority.requirement_kind in _OPEN_FIELDS:
            open_fields.setdefault(authority.address, set()).add(_OPEN_FIELDS[authority.requirement_kind])
    for address, operation in operations.items():
        payload = operation.payload
        identity = known.get(payload.get("name", "")) if operation.resource_type == "node" else None
        if identity is None:
            continue
        values = dict(zip(("os_distribution", "os_version"), identity, strict=True))
        completed = {
            field: values[field]
            for field in open_fields.get(address, ())
            if not payload.get(field)
        }
        if completed:
            operations[address] = replace(operation, payload={**payload, **completed})


__all__ = ["complete_operating_systems"]
