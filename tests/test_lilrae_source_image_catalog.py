"""Trusted source selectors fail closed and never follow registry tags."""

from dataclasses import replace

import pytest
from raes.runtime_configuration import RuntimeConfiguration
from raes_contracts.planning import PlannedResource, RuntimeDomain

from aptl.backends import _raes_backend_implementation_profiles as profiles
from aptl.backends.raes_image_realization import resolve_node_image


def _resolve(tmp_path, name, version, **node_fields):
    payload = {
        "spec": {"node": {"source": {"name": name, "version": version}, **node_fields}}
    }
    resource = PlannedResource(
        address="provision.node.arbitrary",
        domain="provisioning",
        resource_type="node",
        payload=payload,
    )
    diagnostics = []
    image = resolve_node_image(
        resource=resource,
        payload=payload,
        project_dir=tmp_path,
        service_name="unrelated-service",
        diagnostics=diagnostics,
    )
    return image, diagnostics


def test_catalog_selects_existing_immutable_image_with_provenance(tmp_path):
    image, diagnostics = _resolve(tmp_path, "wazuh/wazuh-manager", "4.12.0")
    assert not diagnostics
    assert image.policy_rule == "trusted-source-catalog"
    assert "@sha256:" in image.image_ref
    assert image.source_name == "wazuh/wazuh-manager"
    assert image.source_version == "4.12.0"
    assert image.catalog_record == "wazuh-manager-4.12"
    assert image.provenance_refs
    assert image.catalog_revision.startswith("sha256:")


@pytest.mark.parametrize(
    "name,version",
    [
        ("bind9", "9"),
        ("postgresql", "17"),
        ("postgres", "16"),
        ("nginx", "stable"),
        ("wazuh-manager", "4"),
        ("wazuh-indexer", "4"),
        ("wazuh-dashboard", "4"),
        ("thehive", "5"),
        ("opensearch", "2"),
    ],
)
def test_released_kit_selector_resolves_to_a_reviewed_pin(tmp_path, name, version):
    image, diagnostics = _resolve(tmp_path, name, version)
    assert not diagnostics
    assert image is not None
    assert "@sha256:" in image.image_ref
    assert image.provenance_refs
    assert image.source_name == name
    assert image.source_version == version


@pytest.mark.parametrize("name,version", [("postgresql", "17"), ("gitea", "1")])
def test_catalog_runtime_facts_constrain_new_source_records(tmp_path, name, version):
    runtime = RuntimeConfiguration.model_validate(
        {
            "datastore_services": [
                {
                    "datastore_service_id": "contradiction",
                    "engine": "redis",
                    "version": "7",
                }
            ]
        }
    )
    image, diagnostics = _resolve(
        tmp_path, name, version, runtime=runtime.model_dump(mode="json")
    )
    assert image is None
    assert any("incompatible-source" in d.message for d in diagnostics)


@pytest.mark.parametrize(
    "source,version,collection,records",
    [
        (
            "postgresql",
            "17",
            "database_services",
            [
                {"database_service_id": "db", "engine": "postgresql", "version": "16"},
            ],
        ),
        (
            "gitea",
            "1",
            "database_services",
            [
                {"database_service_id": "db", "engine": "postgresql", "version": "17"},
            ],
        ),
        (
            "postgresql",
            "17",
            "database_services",
            [
                {"database_service_id": "a", "engine": "postgresql", "version": "17"},
                {"database_service_id": "b", "engine": "postgresql", "version": "16"},
            ],
        ),
        (
            "cassandra",
            "5",
            "datastore_services",
            [
                {"datastore_service_id": "a", "engine": "cassandra", "version": "5"},
                {"datastore_service_id": "b", "engine": "redis", "version": "7"},
            ],
        ),
        (
            "thehive",
            "5",
            "platform_applications",
            [
                {
                    "platform_application_id": "a",
                    "product": "TheHive",
                    "version": "5.4",
                },
                {
                    "platform_application_id": "b",
                    "product": "Cortex",
                    "version": "3.1.8",
                },
            ],
        ),
        (
            "python",
            "3.12",
            "software_components",
            [
                {"component_id": "python", "name": "Python", "version": "3.12"},
                {"component_id": "nodejs", "name": "Node.js", "version": "22"},
            ],
        ),
        (
            "wazuh-manager",
            "4",
            "security_monitoring_managers",
            [
                {
                    "security_monitoring_manager_id": "a",
                    "implementation": "wazuh",
                    "version": "4.12.0",
                },
                {
                    "security_monitoring_manager_id": "b",
                    "implementation": "wazuh",
                    "version": "4.11.0",
                },
            ],
        ),
    ],
)
def test_source_catalog_rejects_conflicting_typed_product_facts(
    tmp_path, source, version, collection, records
):
    runtime = RuntimeConfiguration.model_validate({collection: records})
    image, diagnostics = _resolve(
        tmp_path, source, version, runtime=runtime.model_dump(mode="json")
    )
    assert image is None
    assert any("incompatible-source" in d.message for d in diagnostics)


def test_source_catalog_rejects_conflict_in_another_product_collection(tmp_path):
    image, diagnostics = _resolve(
        tmp_path,
        "cassandra",
        "5",
        runtime={
            "datastore_services": [
                {"datastore_service_id": "db", "engine": "cassandra", "version": "5"},
            ],
            "database_services": [
                {"database_service_id": "db", "engine": "postgresql", "version": "17"},
            ],
        },
    )
    assert image is None
    assert any("incompatible-source" in d.message for d in diagnostics)


@pytest.mark.parametrize(
    "reference",
    [
        "https://user:password@example.test/image@sha256:" + "a" * 64,
        "--option@sha256:" + "a" * 64,
        "trusted/image@sha256:" + "a" * 64 + "\n",
    ],
)
def test_invalid_catalog_references_fail_closed_without_value_leak(
    tmp_path, monkeypatch, reference
):
    original = next(
        p
        for p in profiles.BACKEND_IMPLEMENTATION_PROFILES
        if p.profile_id == "wazuh-manager-4.12"
    )
    monkeypatch.setattr(
        profiles,
        "BACKEND_IMPLEMENTATION_PROFILES",
        (replace(original, image_ref=reference),),
    )
    image, diagnostics = _resolve(
        tmp_path, original.source_name, original.source_version
    )
    assert image is None
    assert any("invalid-catalog-entry" in d.message for d in diagnostics)
    assert all(reference not in d.message for d in diagnostics)


@pytest.mark.parametrize(
    "name,version",
    [
        ("postgres", "stable"),
        ("unknown", "1"),
        ("postgresql", "*"),
        ("postgresql", ""),
        ("WAZUH-MANAGER", "4"),
    ],
)
def test_catalog_misses_never_fall_back_to_mutable_tags(tmp_path, name, version):
    image, diagnostics = _resolve(tmp_path, name, version)
    assert image is None
    assert any("unknown-source" in d.message for d in diagnostics)


def test_windows_source_refused(tmp_path):
    image, diagnostics = _resolve(tmp_path, "windows-server", "2022")
    assert image is None
    assert any("unsupported-windows-source" in d.message for d in diagnostics)


def test_duplicate_catalog_records_are_ambiguous(tmp_path, monkeypatch):
    original = next(
        p
        for p in profiles.BACKEND_IMPLEMENTATION_PROFILES
        if p.profile_id == "wazuh-manager-4.12"
    )
    monkeypatch.setattr(
        profiles,
        "BACKEND_IMPLEMENTATION_PROFILES",
        (
            original,
            replace(original, profile_id="another-policy"),
        ),
    )
    image, diagnostics = _resolve(
        tmp_path, original.source_name, original.source_version
    )
    assert image is None
    assert any("ambiguous-source" in d.message for d in diagnostics)


def test_contradictory_runtime_fails_instead_of_selecting_another_product(tmp_path):
    runtime = RuntimeConfiguration.model_validate(
        {
            "datastore_services": [
                {
                    "datastore_service_id": "database",
                    "engine": "redis",
                    "version": "7",
                }
            ]
        }
    )
    image, diagnostics = _resolve(
        tmp_path, "cassandra", "4.1", runtime=runtime.model_dump(mode="json")
    )
    assert image is None
    assert any("incompatible-source" in d.message for d in diagnostics)


def test_declared_os_must_be_supported_by_selected_catalog_record(tmp_path):
    image, diagnostics = _resolve(
        tmp_path, "cassandra", "4.1", os="windows", os_version="2022"
    )
    assert image is None
    assert any("incompatible-source" in d.message for d in diagnostics)


def _provisioner_plan(
    tmp_path, name="wazuh/wazuh-manager", version="4.12.0", *, open_substrate=True
):
    from unittest.mock import MagicMock
    from raes_contracts.planning import (
        ProvisioningPlan,
        PlannedRealizationConstraint,
        ProvisionOp,
        ChangeAction,
    )
    from aptl.backends.raes_provisioner import AptlProvisioner
    from aptl.core.config import AptlConfig
    from aptl.core.scenario_bundle import project_tree_bundle

    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  arbitrary:\n    image: unused:local\n    profiles: [wazuh]\n"
    )
    payload = {
        "name": "arbitrary",
        "spec": {
            "node": {
                "name": "arbitrary",
                "source": {"name": name, "version": version},
            },
            "infrastructure": {},
        },
    }
    resource = PlannedResource(
        address="provision.node.arbitrary",
        domain=RuntimeDomain.PROVISIONING,
        resource_type="node",
        payload=payload,
    )
    constraints = (
        (
            PlannedRealizationConstraint(
                address=resource.address,
                field_path="nodes.arbitrary.realization.compute_substrate",
                concern="compute-substrate",
                posture="open",
                value_domain=None,
                governing_scope="#/realization",
                provenance="author-declared",
            ),
        )
        if open_substrate
        else ()
    )
    plan = ProvisioningPlan(
        resources={resource.address: resource},
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address=resource.address,
                resource_type="node",
                payload=payload,
            )
        ],
        realization_constraints=constraints,
    )
    provisioner = AptlProvisioner(
        project_dir=tmp_path,
        config=AptlConfig(lab={"name": "test"}, containers={"wazuh": True}),
        bundle=project_tree_bundle(tmp_path, tmp_path / "demo.sdl.yaml"),
        deployment_backend=MagicMock(),
    )
    return provisioner, plan


def test_catalog_requires_open_substrate_in_shared_admission(tmp_path):
    provisioner, plan = _provisioner_plan(tmp_path, open_substrate=False)
    assert any("source-not-authorized" in d.message for d in provisioner.validate(plan))
    provisioner.deployment_backend.realize.assert_not_called()


@pytest.mark.parametrize(
    "name,version,reason",
    [
        ("unrecognized", "1", "unknown-source"),
        ("windows-server", "2022", "unsupported-windows-source"),
    ],
)
def test_invalid_source_refused_before_apply_mutations(tmp_path, name, version, reason):
    from raes_contracts.runtime_state import RuntimeSnapshot

    provisioner, plan = _provisioner_plan(tmp_path, name, version)
    assert any(reason in d.message for d in provisioner.validate(plan))
    baseline = RuntimeSnapshot()
    result = provisioner.apply(plan, baseline)
    assert not result.success
    assert result.snapshot == baseline
    provisioner.deployment_backend.realize.assert_not_called()


def test_released_linux_kit_inventory_has_complete_catalog_coverage(tmp_path):
    import json
    from pathlib import Path

    inventory = json.loads(
        (
            Path(__file__).parent
            / "fixtures"
            / "lilrae_source_image_inventory_v6_3_1.json"
        ).read_text()
    )
    missing = set()
    for row in inventory["nodes"]:
        source = row["source"]
        image, diagnostics = _resolve(
            tmp_path,
            source["name"],
            source["version"],
            os=row["os"],
            os_version=row["os_version"],
            runtime=row["runtime"],
        )
        if source["name"] == "windows-server":
            assert image is None
            assert any("unsupported-windows-source" in d.message for d in diagnostics)
        elif image is None or diagnostics:
            missing.add((source["name"], source["version"]))
    assert not missing, (
        f"{inventory['release']} catalog coverage gaps: {sorted(missing)}"
    )
