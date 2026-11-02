"""Generated prerequisites introduced by admitted backend profiles."""

from __future__ import annotations

from raes.runtime_configuration import RuntimeConfiguration
from raes_contracts.planning import PlannedResource

from aptl.core.deployment._misp_cache_credential import (
    MISP_CACHE_CONFIG_MOUNT_DESTINATION,
    MISP_CACHE_CONFIG_OUTPUT,
    MISP_CACHE_CONFIG_RELPATH,
    MISP_CACHE_CREDENTIAL_PROFILE,
    MISP_CACHE_PASSWORD_OUTPUT,
)
from aptl.core.deployment._misp_fastcgi_loopback import (
    MISP_FASTCGI_LOOPBACK_FILENAME,
    MISP_FASTCGI_LOOPBACK_MOUNT_DESTINATION,
    MISP_FASTCGI_LOOPBACK_OUTPUT,
    MISP_FASTCGI_LOOPBACK_PROFILE,
)
from aptl.core.deployment._misp_server_tls import (
    MISP_SERVER_TLS_CERTIFICATE_OUTPUT,
    MISP_SERVER_TLS_MOUNT_DESTINATION,
    MISP_SERVER_TLS_PRIVATE_KEY_OUTPUT,
    MISP_SERVER_TLS_PROFILE,
    MISP_WEB_COMPANION_ROLE,
)
from aptl.core.deployment._companion_realization import companion_service_name
from aptl.core.deployment.realization import (
    DeploymentGeneratedArtifactEnvironmentConsumer,
    DeploymentGeneratedArtifactOutput,
    DeploymentGeneratedArtifactRealization,
    DeploymentStatefulConsumer,
)

_MISP_CACHE_BINDING_ROLE = "data_source"


def selected_generated_artifacts(
    *,
    profile_id: str,
    resource: PlannedResource,
    service_name: str,
    additions: dict[str, object],
    runtime: RuntimeConfiguration,
) -> tuple[DeploymentGeneratedArtifactRealization, ...]:
    """Return prerequisites introduced by an admitted backend selection."""

    artifacts: list[DeploymentGeneratedArtifactRealization] = []
    if profile_id == "misp-2.5.50" and "runtime-environment" in additions:
        artifacts.extend(
            _misp_cache_credential_artifacts(
                resource=resource, service_name=service_name, runtime=runtime
            )
        )
    if profile_id == "misp-2.5.50":
        # Every selection of this profile runs the web companion, and the core
        # image listens for FastCGI on all interfaces by default. The TLS leaf
        # and the loopback override do not depend on an authored environment.
        artifacts.append(_misp_server_tls_artifact(resource, service_name))
        artifacts.append(_misp_fastcgi_loopback_artifact(resource, service_name))
    return tuple(artifacts)


def _misp_server_tls_artifact(
    resource: PlannedResource, service_name: str
) -> DeploymentGeneratedArtifactRealization:
    """Deliver the authored MISP leaf to the web companion that serves TLS."""

    return DeploymentGeneratedArtifactRealization(
        address="backend.generated-artifact.misp-server-tls",
        name="misp-server-tls",
        generator="rendered_config",
        lifecycle="reuse_valid",
        provenance=MISP_SERVER_TLS_PROFILE,
        outputs=(
            DeploymentGeneratedArtifactOutput(
                name=MISP_SERVER_TLS_CERTIFICATE_OUTPUT,
                path="cert.pem",
                sensitivity="public",
            ),
            DeploymentGeneratedArtifactOutput(
                name=MISP_SERVER_TLS_PRIVATE_KEY_OUTPUT,
                path="key.pem",
                sensitivity="secret",
            ),
        ),
        consumers=(
            DeploymentStatefulConsumer(
                target_address=resource.address,
                node_name=resource.address.rsplit(".", 1)[-1],
                service_name=companion_service_name(
                    service_name, MISP_WEB_COMPANION_ROLE
                ),
                mount_destination=MISP_SERVER_TLS_MOUNT_DESTINATION,
                access_mode="read_only",
                selected_outputs=(
                    MISP_SERVER_TLS_CERTIFICATE_OUTPUT,
                    MISP_SERVER_TLS_PRIVATE_KEY_OUTPUT,
                ),
            ),
        ),
    )


def _misp_fastcgi_loopback_artifact(
    resource: PlannedResource, service_name: str
) -> DeploymentGeneratedArtifactRealization:
    """Bind the selected image's FastCGI listener to loopback."""

    return DeploymentGeneratedArtifactRealization(
        address="backend.generated-artifact.misp-fastcgi-loopback",
        name="misp-fastcgi-loopback",
        generator="rendered_config",
        lifecycle="reuse_valid",
        provenance=MISP_FASTCGI_LOOPBACK_PROFILE,
        outputs=(
            DeploymentGeneratedArtifactOutput(
                name=MISP_FASTCGI_LOOPBACK_OUTPUT,
                path=MISP_FASTCGI_LOOPBACK_FILENAME,
                sensitivity="public",
            ),
        ),
        consumers=(
            DeploymentStatefulConsumer(
                target_address=resource.address,
                node_name=resource.address.rsplit(".", 1)[-1],
                service_name=service_name,
                mount_destination=MISP_FASTCGI_LOOPBACK_MOUNT_DESTINATION,
                access_mode="read_only",
                selected_outputs=(MISP_FASTCGI_LOOPBACK_OUTPUT,),
            ),
        ),
    )


def _misp_cache_credential_artifacts(
    *,
    resource: PlannedResource,
    service_name: str,
    runtime: RuntimeConfiguration,
) -> list[DeploymentGeneratedArtifactRealization]:
    """Build the cache credential for MISP's one authored cache binding."""

    cache_node = _bound_cache_node(runtime)
    if cache_node is None:
        return []
    return [
        DeploymentGeneratedArtifactRealization(
            address="backend.generated-artifact.misp-cache-credential",
            name="misp-cache-credential",
            generator="rendered_config",
            lifecycle="reuse_valid",
            provenance=MISP_CACHE_CREDENTIAL_PROFILE,
            outputs=(
                DeploymentGeneratedArtifactOutput(
                    name=MISP_CACHE_PASSWORD_OUTPUT,
                    path="cache-password",
                    sensitivity="secret",
                    disposition="producer_private",
                ),
                DeploymentGeneratedArtifactOutput(
                    name=MISP_CACHE_CONFIG_OUTPUT,
                    path=MISP_CACHE_CONFIG_RELPATH,
                    sensitivity="secret",
                ),
            ),
            consumers=(
                DeploymentStatefulConsumer(
                    target_address=f"provision.node.{cache_node}",
                    node_name=cache_node,
                    service_name=cache_node,
                    mount_destination=MISP_CACHE_CONFIG_MOUNT_DESTINATION,
                    access_mode="read_only",
                    selected_outputs=(MISP_CACHE_CONFIG_OUTPUT,),
                ),
            ),
            environment_consumers=(
                DeploymentGeneratedArtifactEnvironmentConsumer(
                    target_address=resource.address,
                    node_name=resource.address.rsplit(".", 1)[-1],
                    service_name=service_name,
                    output_name=MISP_CACHE_PASSWORD_OUTPUT,
                    environment_variable="REDIS_PASSWORD",
                ),
            ),
        )
    ]


def _bound_cache_node(runtime: RuntimeConfiguration) -> str | None:
    """Return the single cache node MISP's authored bindings point at."""

    targets = {
        str(binding.target_node_ref)
        for application in getattr(runtime, "platform_applications", ())
        for binding in getattr(application, "upstream_bindings", ())
        if str(getattr(binding.role, "value", binding.role))
        == _MISP_CACHE_BINDING_ROLE
        and str(getattr(binding, "target_service_ref", "")) == "redis"
        and str(getattr(binding, "target_node_ref", ""))
    }
    return targets.pop() if len(targets) == 1 else None


__all__ = ("selected_generated_artifacts",)
