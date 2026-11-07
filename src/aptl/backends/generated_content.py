"""Join admitted content references to generated outputs without reading values."""

from dataclasses import replace
import hmac
from pathlib import Path
from typing import TYPE_CHECKING

from aptl.backends.raes_realization_model import PlacementRealization
from aptl.core.deployment.random_values import random_value_directory
from aptl.core.deployment.realization import DeploymentGeneratedArtifactRealization
from aptl.core.deployment.realization import DeploymentContentRealization
from aptl.core.deployment.errors import BackendTimeoutError
from aptl.utils.pathsafe import PathContainmentError, read_contained_nofollow
from raes_contracts.diagnostics import Diagnostic

if TYPE_CHECKING:
    from aptl.core.deployment.backend import DeploymentBackend


def bind_generated_content(
    placements: list[PlacementRealization],
    artifacts: list[DeploymentGeneratedArtifactRealization],
    diagnostics: list[Diagnostic],
) -> list[PlacementRealization]:
    """Bind only the selected, consumer-visible output of an admitted artifact."""

    by_name = {artifact.name: artifact for artifact in artifacts}
    bound = []
    for placement in placements:
        content = placement.content
        if content is None or content.generated_value_source is None:
            bound.append(placement)
            continue
        source = content.generated_value_source
        artifact = by_name.get(
            source.generated_artifact.removeprefix("generated_artifacts.")
        )
        output = (
            next(
                (item for item in artifact.outputs if item.name == source.output), None
            )
            if artifact is not None
            else None
        )
        if (
            artifact is None
            or artifact.generator != "random_value"
            or output is None
            or output.disposition == "producer_private"
            or (output.sensitivity == "secret" and not content.sensitive)
            or not any(
                consumer.target_address == placement.address
                and consumer.output == output.name
                for consumer in artifact.content_consumers
            )
        ):
            diagnostics.append(
                Diagnostic(
                    code="aptl.provisioner.generated-content-invalid",
                    address=placement.address,
                    domain="provisioning",
                    message="Generated content has no admitted consumer-visible output.",
                )
            )
            continue
        relative = (
            random_value_directory(artifact.address, artifact.scope_binding)
            / "outputs"
            / output.path
        )
        bound.append(
            replace(
                placement, content=replace(content, source_relpath=relative.as_posix())
            )
        )
    return bound


def generated_content_delivered(
    backend: DeploymentBackend,
    container: str,
    content: DeploymentContentRealization,
    realization_root: Path,
) -> bool:
    """Compare the delivered bytes privately; return no generated value or digest."""

    if content.source_relpath is None:
        return False
    try:
        expected = read_contained_nofollow(realization_root, content.source_relpath)
        actual = backend.container_file_read(
            container,
            "/" + content.dest_relpath.lstrip("/"),
            max_bytes=len(expected) + 1,
        )
    except BackendTimeoutError, OSError, ValueError, PathContainmentError:
        return False
    return isinstance(actual, bytes) and hmac.compare_digest(actual, expected)
