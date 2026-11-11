"""Backend companion containers that join an owner node's network namespace."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from aptl.core.deployment._realization_primitives import DeploymentImageRealization

if TYPE_CHECKING:
    from aptl.core.deployment.realization import DeploymentRealizationSpec


@dataclass(frozen=True)
class DeploymentCompanionRealization(object):
    """One backend-owned container that joins its owner node's network namespace.

    The owner keeps the node's network identity, addresses, and published
    ports; the companion only serves part of the node's declared surface. Its
    ``image.service_name`` is the companion's Compose service.
    """

    role: str
    image: DeploymentImageRealization
    environment: tuple[tuple[str, str], ...] = ()
    tmpfs: tuple[str, ...] = ()


def companion_service_name(owner_service: str, role: str) -> str:
    """Return the Compose service name of one owner node's companion."""

    return f"{owner_service}-{role}"


def companion_container_name(owner_container: str, role: str) -> str:
    """Return the semantic container name of one owner node's companion."""

    return f"{owner_container}-{role}"


def companion_images(
    spec: DeploymentRealizationSpec,
) -> tuple[DeploymentImageRealization, ...]:
    """Return every companion image the realization must obtain and verify."""

    return tuple(
        companion.image
        for node in spec.nodes
        for companion in node.backend_companions
    )


def with_companion_services(
    spec: DeploymentRealizationSpec, services: tuple[str, ...]
) -> tuple[str, ...]:
    """Return ``services`` plus the companions of every named owner service.

    Compose starts the ``depends_on`` closure of a named service, never its
    dependents, and a companion depends on its owner's network namespace. A
    phased start that names an owner must therefore name its companions too.
    """

    added = tuple(
        companion.image.service_name
        for node in spec.nodes
        if node.service_name in services
        for companion in node.backend_companions
    )
    return tuple(sorted({*services, *added}))
