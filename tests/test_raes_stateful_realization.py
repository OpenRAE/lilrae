"""Tests for RAES generated-artifact and persistent-volume lowering."""

from __future__ import annotations

from pathlib import Path
from dataclasses import replace

from raes_contracts.planning import (
    ChangeAction,
    PlannedResource,
    ProvisioningPlan,
    ProvisionOp,
    RuntimeDomain,
    RealizationAuthorityMode,
    RealizationResolutionSource,
    ResolvedRealizationAuthority,
)

from aptl.backends.raes_manifest import create_aptl_manifest
from aptl.backends.raes_realization import interpret_provisioning_plan
from aptl.core.config import AptlConfig
from aptl.core.scenario_bundle import ScenarioBundle, project_tree_bundle


def _bundle(root: Path) -> ScenarioBundle:
    return project_tree_bundle(root, root / "scenarios" / "demo.sdl.yaml")


def _resource(
    resource_type: str,
    name: str,
    spec: dict[str, object],
    *,
    ordering_dependencies: tuple[str, ...] = (),
) -> PlannedResource:
    address = f"provision.{resource_type}.{name}"
    return PlannedResource(
        address=address,
        domain=RuntimeDomain.PROVISIONING,
        resource_type=resource_type,
        payload={"name": name, "spec": spec},
        ordering_dependencies=ordering_dependencies,
    )


def _node(name: str) -> PlannedResource:
    return _resource(
        "node",
        name,
        {
            "node": {"name": name},
            "infrastructure": {},
        },
    )


def _plan(*resources: PlannedResource) -> ProvisioningPlan:
    mapped = {resource.address: resource for resource in resources}
    return ProvisioningPlan(
        resources=mapped,
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address=resource.address,
                resource_type=resource.resource_type,
                payload=resource.payload,
                ordering_dependencies=resource.ordering_dependencies,
                refresh_dependencies=resource.refresh_dependencies,
            )
            for resource in resources
        ],
    )


def _write_compose(project_dir: Path) -> None:
    (project_dir / "docker-compose.yml").write_text(
        """services:
  wazuh-indexer:
    profiles: [wazuh]
    image: wazuh/wazuh-indexer:4.12.0
  wazuh-manager:
    profiles: [wazuh]
    image: wazuh/wazuh-manager:4.12.0
"""
    )


def _config() -> AptlConfig:
    return AptlConfig(lab={"name": "test"}, containers={'profiles': ['wazuh', 'victim', 'kali', 'enterprise', 'soc', 'fileshare', 'dns']})


def test_manifest_advertises_released_stateful_contract() -> None:
    manifest = create_aptl_manifest()

    assert manifest.provisioner.supports_generated_artifacts is True
    assert {
        str(getattr(mode, "value", mode))
        for mode in manifest.provisioner.supported_generated_artifact_delivery_modes
    } == {"mount", "environment"}
    assert manifest.provisioner.supports_persistent_volumes is True


def test_resolved_environment_authority_reaches_binding_admission(tmp_path: Path) -> None:
    """Deployment must retain RAES authority rather than infer it from values."""

    _write_compose(tmp_path)
    node = _node("wazuh-indexer")
    authority = ResolvedRealizationAuthority(
        address=node.address,
        field_path="nodes.wazuh-indexer.runtime.environment",
        domain="runtime-realization",
        requirement_kind="runtime-environment",
        payload_pointer="/spec/node/runtime/environment",
        mode=RealizationAuthorityMode.CLOSED,
        source=RealizationResolutionSource.AUTHORED_SCOPE,
    )
    plan = replace(_plan(node), realization_authority=(authority,))
    realization = interpret_provisioning_plan(plan=plan, config=_config(), bundle=_bundle(tmp_path))
    assert realization.realization_authority == (authority,)
    assert realization.deployment_spec([]).realization_authority == (authority,)


def test_interpreter_lowers_stateful_resources_into_deployment_spec(
    tmp_path: Path,
) -> None:
    _write_compose(tmp_path)
    artifact = _resource(
        "generated-artifact",
        "wazuh-indexer-certs",
        {
            "generator": "certificate_bundle",
            "lifecycle": "reuse_valid",
            "provenance": "config/certs.yml",
            "outputs": [
                {"name": "root-ca", "path": "root-ca.pem", "sensitivity": "public"},
                {
                    "name": "indexer-key",
                    "path": "wazuh.indexer-key.pem",
                    "sensitivity": "secret",
                },
            ],
            "consumers": [
                {
                    "node": "wazuh-indexer",
                    "target_address": "provision.node.wazuh-indexer",
                    "mount_destination": "/usr/share/wazuh-indexer/certs",
                    "access_mode": "read_only",
                }
            ],
        },
    )
    volume = _resource(
        "persistent-volume",
        "wazuh-indexer-data",
        {
            "lifecycle": "retain",
            "access_mode": "read_write_once",
            "consumers": [
                {
                    "node": "wazuh-indexer",
                    "target_address": "provision.node.wazuh-indexer",
                    "mount_destination": "/var/lib/wazuh-indexer",
                    "access_mode": "read_write",
                }
            ],
        },
        ordering_dependencies=(artifact.address,),
    )

    realization = interpret_provisioning_plan(
        plan=_plan(_node("wazuh-indexer"), _node("wazuh-manager"), artifact, volume),
        config=_config(),
        bundle=_bundle(tmp_path),
    )

    assert [item.code for item in realization.diagnostics] == []
    assert len(realization.generated_artifacts) == 1
    assert len(realization.persistent_volumes) == 1
    generated = realization.generated_artifacts[0]
    assert generated.address == artifact.address
    assert generated.generator == "certificate_bundle"
    assert generated.outputs[1].sensitivity == "secret"
    assert generated.consumers[0].service_name == "wazuh-indexer"
    assert generated.consumers[0].delivery_mode == "mount"
    persistent = realization.persistent_volumes[0]
    assert persistent.ordering_dependencies == (artifact.address,)
    assert persistent.consumers[0].mount_destination == "/var/lib/wazuh-indexer"

    spec = realization.deployment_spec(["wazuh", "otel"])
    assert spec.generated_artifacts == realization.generated_artifacts
    assert spec.persistent_volumes == realization.persistent_volumes


def test_interpreter_lowers_generated_environment_consumers(tmp_path: Path) -> None:
    """RAES 4.1 environment delivery remains an authored artifact binding."""

    _write_compose(tmp_path)
    artifact = _resource(
        "generated-artifact",
        "misp-cache-credential",
        {
            "generator": "rendered_config",
            "lifecycle": "reuse_valid",
            "provenance": "techvault:misp-cache-credential/v2",
            "outputs": [
                {
                    "name": "cache-password",
                    "path": "cache-password",
                    "sensitivity": "secret",
                }
            ],
            "consumers": [],
            "environment_consumers": [
                {
                    "node": "wazuh-indexer",
                    "target_address": "provision.node.wazuh-indexer",
                    "delivery_mode": "environment",
                    "output": "cache-password",
                    "environment_variable": "REDIS_PASSWORD",
                }
            ],
        },
    )

    realization = interpret_provisioning_plan(
        plan=_plan(_node("wazuh-indexer"), artifact),
        config=_config(),
        bundle=_bundle(tmp_path),
    )

    assert [item.code for item in realization.diagnostics] == []
    generated = realization.generated_artifacts[0]
    assert generated.consumers == ()
    assert generated.environment_consumers[0].environment_variable == "REDIS_PASSWORD"
    assert generated.environment_consumers[0].output_name == "cache-password"


def test_interpreter_rejects_environment_consumer_name_injection(
    tmp_path: Path,
) -> None:
    _write_compose(tmp_path)
    artifact = _resource(
        "generated-artifact",
        "misp-cache-credential",
        {
            "generator": "rendered_config",
            "lifecycle": "reuse_valid",
            "provenance": "techvault:misp-cache-credential/v2",
            "outputs": [
                {
                    "name": "cache-password",
                    "path": "cache-password",
                    "sensitivity": "secret",
                }
            ],
            "consumers": [],
            "environment_consumers": [
                {
                    "node": "wazuh-indexer",
                    "target_address": "provision.node.wazuh-indexer",
                    "delivery_mode": "environment",
                    "output": "cache-password",
                    "environment_variable": "SAFE\nINJECTED",
                }
            ],
        },
    )

    realization = interpret_provisioning_plan(
        plan=_plan(_node("wazuh-indexer"), artifact),
        config=_config(),
        bundle=_bundle(tmp_path),
    )

    assert realization.generated_artifacts == ()
    assert "aptl.provisioner.stateful-resource-invalid" in {
        item.code for item in realization.diagnostics
    }


def test_interpreter_rejects_unknown_stateful_consumer_before_backend(
    tmp_path: Path,
) -> None:
    _write_compose(tmp_path)
    artifact = _resource(
        "generated-artifact",
        "orphaned-config",
        {
            "generator": "rendered_config",
            "lifecycle": "regenerate_on_change",
            "provenance": "config/wazuh-manager.conf.template",
            "outputs": [
                {
                    "name": "manager-conf",
                    "path": "ossec.conf",
                    "sensitivity": "restricted",
                }
            ],
            "consumers": [
                {
                    "node": "missing",
                    "target_address": "provision.node.missing",
                    "mount_destination": "/var/ossec/etc/ossec.conf",
                    "access_mode": "read_only",
                }
            ],
        },
    )

    realization = interpret_provisioning_plan(
        plan=_plan(_node("wazuh-indexer"), artifact),
        config=_config(),
        bundle=_bundle(tmp_path),
    )

    assert realization.generated_artifacts == ()
    assert any(
        item.code == "aptl.provisioner.stateful-consumer-unresolved"
        for item in realization.diagnostics
    )
