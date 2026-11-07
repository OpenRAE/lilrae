"""Read back the initial Docker orchestration endpoint and selected policy."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aptl.backends.raes_realization_model import NodeRealization
    from aptl.core.deployment.backend import DeploymentBackend

from aptl.backends._raes_runtime_local_control_observation import (
    observe_local_control_interfaces,
    recorded_socket_source,
)
from aptl.backends._runtime_concern_disclosure import _disclose
from aptl.backends.raes_runtime_orchestration import docker_control_authorities
from aptl.backends.service_inventory import container_environment


def observe_orchestration_authorities(
    backend: DeploymentBackend, node: NodeRealization, nodes: Sequence[NodeRealization]
) -> object | None:
    runtime = node.runtime
    if not runtime.orchestration_authorities:
        return None
    bindings = docker_control_authorities(runtime, node_address=node.address)
    info = backend.container_inspect(node.container_name)
    if (
        observe_local_control_interfaces(
            info,
            runtime,
            recording_source=recorded_socket_source(backend, node.container_name),
        )
        is None
    ):
        return None
    env = container_environment(info)
    for authority, interface in bindings:
        if authority.scope is not None and (
            authority.scope.organization_ref
            or authority.scope.environment_name != env.get("ENVIRONMENT_NAME")
        ):
            return None
        policy = authority.lifecycle_policy
        if policy is not None and (
            policy.timeout
            or policy.execution_timeout != env.get("SHUFFLE_ORBORUS_EXECUTION_TIMEOUT")
            or policy.cleanup != env.get("CLEANUP")
        ):
            return None
        for template in authority.spawn_templates:
            if (
                template.image_ref
                and backend.substrate_image_identity(template.image_ref) is None
            ):
                return None
        if authority.realized_children:
            return None  # no initial claim about subsequent spawned workloads
    return _disclose(
        "runtime-orchestration-authorities",
        [r.model_dump(mode="json") for r in runtime.orchestration_authorities],
    )
