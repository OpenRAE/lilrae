"""Correlate backend catalog selections with independent container readback."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from aptl.core.deployment._docker_image_identity import _IMAGE_ID

if TYPE_CHECKING:
    from aptl.backends._raes_observation_helpers import ObservedResource
    from aptl.backends.raes_realization_model import AptlRealization
    from aptl.core.deployment.backend import DeploymentBackend
    from aptl.core.deployment.observation import DeploymentObservationContext


def observe_catalog_images(
    backend: DeploymentBackend,
    realization: AptlRealization,
    observations: dict[str, ObservedResource],
    observation_context: DeploymentObservationContext | None = None,
) -> None:
    """Gate catalog nodes without manufacturing authored artifact demands."""

    for node in realization.nodes:
        image = node.image
        observed = observations.get(node.address)
        if image is None or image.catalog_record is None or observed is None:
            continue
        container = node.container_name or ""
        config, digest = _observed_image_identity(
            backend, container, image.image_ref, observation_context
        )
        expected = image.image_ref.rsplit("@", 1)[-1]
        verified = observed.realized and config is not None and digest == expected
        evidence = {
            "declared_source": {
                "name": image.source_name,
                "version": image.source_version,
            },
            "catalog_record": image.catalog_record,
            "catalog_revision": image.catalog_revision,
            "provenance_refs": list(image.provenance_refs),
            "selected_image_ref": image.image_ref,
            "selected_digest": expected,
            "selected_digest_domain": "registry-repo-digest",
            "observed_config_digest": config,
            "observed_digest_domain": "docker-image-config",
            # This digest is proven by the actual image's RepoDigests, not
            # read directly from .Image (which identifies different bytes).
            "verified_manifest_digest": digest if verified else None,
            "verified": verified,
        }
        observations[node.address] = replace(
            observed,
            realized=observed.realized and verified,
            evidence={**observed.evidence, "source_image": evidence},
        )


def _observed_image_identity(
    backend: DeploymentBackend,
    container: str,
    image_ref: str,
    observation_context: DeploymentObservationContext | None,
) -> tuple[str | None, str | None]:
    """Read live identity or correlated proof for a verified absent container."""

    config = backend.container_image_config_id(container) if container else None
    completed = (
        _completed_image_identity(backend, container, image_ref, observation_context)
        if config is None
        else None
    )
    if completed:
        return completed
    if not isinstance(config, str) or not _IMAGE_ID.fullmatch(config):
        return None, None
    return config, backend.container_image_digest(
        container, expected_ref=image_ref, expected_config_id=config
    )


def _completed_image_identity(
    backend: DeploymentBackend,
    container: str,
    image_ref: str,
    observation_context: DeploymentObservationContext | None,
) -> tuple[str, str] | None:
    """Accept valid completion proof only while the container remains absent."""

    if observation_context is None:
        return None
    identity = observation_context.completed_selected_image_identity(
        container, image_ref
    )
    if (
        identity is None
        or not isinstance(identity[0], str)
        or not _IMAGE_ID.fullmatch(identity[0])
    ):
        return None
    # An unreadable image ID does not prove absence. A reappearing live
    # container must not inherit a completed container's identity receipt.
    return identity if not backend.container_inspect(container) else None


def catalog_images_unverified(
    observations: dict[str, ObservedResource],
) -> tuple[str, ...]:
    """Return failed catalog bindings for the existing apply error boundary."""

    return tuple(
        address
        for address, observed in observations.items()
        if isinstance((evidence := observed.evidence.get("source_image")), dict)
        and evidence.get("verified") is not True
    )
