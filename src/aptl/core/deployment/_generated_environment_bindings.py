"""Match each runtime value_from to its exact generated-output consumer."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from raes.runtime_configuration import GeneratedArtifactValueSource
    from aptl.core.deployment.realization import (
        DeploymentGeneratedArtifactEnvironmentConsumer,
        DeploymentGeneratedArtifactRealization,
        DeploymentNodeRealization,
        DeploymentRealizationSpec,
    )


def generated_environment_names(
    realization: DeploymentRealizationSpec, node: DeploymentNodeRealization
) -> frozenset[str]:
    """Return only unambiguous artifact/output bindings for this exact node.

    Values do not exist during preflight. Matching their source descriptors
    now prevents a different artifact or output with the same target variable
    from satisfying the declaration. Both container routes use this check.
    """

    bound: set[str] = set()
    for variable in getattr(node.runtime, "environment", ()) or ():
        reference = getattr(variable, "value_from", None)
        if reference is None:
            continue
        candidates = [
            (artifact, consumer)
            for artifact in realization.generated_artifacts
            for consumer in artifact.environment_consumers
            if consumer.target_address == node.address
            and consumer.environment_variable == variable.name
        ]
        if len(candidates) != 1:
            continue
        artifact, consumer = candidates[0]
        if _matches_generated_source(node, artifact, consumer, reference):
            bound.add(variable.name)
    return frozenset(bound)


def _matches_generated_source(
    node: DeploymentNodeRealization,
    artifact: DeploymentGeneratedArtifactRealization,
    consumer: DeploymentGeneratedArtifactEnvironmentConsumer,
    reference: GeneratedArtifactValueSource,
) -> bool:
    """Match the declared source and consumer without reading its value."""

    return (
        artifact.name == reference.generated_artifact
        and consumer.output_name == reference.output
        and consumer.node_name == node.name
        and consumer.service_name == (node.service_name or node.name)
        and any(output.name == reference.output for output in artifact.outputs)
    )
