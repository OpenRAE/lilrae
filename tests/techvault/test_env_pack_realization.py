"""Issue #875: the released TechVault pack realizes cleanly (#1700)."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def techvault_realization(released_techvault_realization):
    """Run the released pack's filesystem-backed planner once per test session."""

    return released_techvault_realization


@pytest.mark.integration
def test_techvault_pack_realizes_without_provisioner_diagnostics(
    techvault_realization,
):
    """Interpreting the pack yields nodes, networks, profiles and no errors."""

    realization = techvault_realization

    codes = sorted({d.code for d in realization.diagnostics})
    assert codes == [], f"unexpected realization diagnostics: {codes}"
    assert len(realization.nodes) >= 21
    assert {"soc", "enterprise", "wazuh"} <= set(realization.profiles)
    evidence = realization.pack_interaction_evidence(sorted(realization.profiles))
    assert evidence["pack"]["pack_id"] == "techvault"
    assert evidence["provider"]["provider_id"] == "techvault-aptl-serving"
    # The adapter ships inside the one distribution, so host-observed
    # provenance names it. What the seam still proves is that the provenance
    # comes from installed metadata rather than the provider's own claim.
    assert evidence["provider"]["distribution"] == "lilrae"
    assert evidence["provider"]["entry_point"] == "techvault.aptl"
    assert evidence["provider"]["mapping_digest"].startswith("sha256:")


@pytest.mark.integration
def test_real_pack_orborus_disables_undeclared_pipeline_startup(techvault_realization):
    """Offline worker startup must not auto-provision a Tenzir/Sigma stack."""
    from aptl.core.deployment._compose_node_generation import render_realization_compose

    spec = techvault_realization.deployment_spec(sorted(techvault_realization.profiles))
    services = render_realization_compose(spec)["services"]
    environment = services["shuffle-orborus"]["environment"]

    assert environment.get("SHUFFLE_SKIP_PIPELINES") == "true"
    assert environment.get("SHUFFLE_STATS_DISABLED") == "true"
    assert environment.get("SHUFFLE_LOGS_DISABLED") == "true"
    assert environment["SHUFFLE_AUTO_IMAGE_DOWNLOAD"] == "false"
    assert "@sha256:" in environment["SHUFFLE_WORKER_IMAGE"]


@pytest.mark.integration
def test_generated_compose_covers_image_nodes_networks_and_ordering(
    techvault_realization, tmp_path
):
    """The generated base compose renders image nodes, networks, and safe deps."""

    from aptl.core.deployment._compose_node_generation import render_realization_compose

    realization = techvault_realization
    # This #875 rendering test is intentionally independent of env-packs #285,
    # which must replace Shuffle's mutable child image and author the realized
    # child correlation before APTL can admit its Docker authority. Strip only
    # that downstream declaration so the generic Compose surface remains covered.
    spec = realization.deployment_spec(sorted(realization.profiles))
    document = render_realization_compose(spec)

    services = document["services"]
    # Image-backed SOC nodes are emitted as services...
    assert "misp" in services
    assert services["misp"]["image"]
    assert services["misp"]["container_name"] == "aptl-misp"
    assert services["misp"]["profiles"] == ["soc"]
    assert services["suricata"]["labels"]["aptl.node.address"] == (
        "provision.node.suricata"
    )
    misp = next(node for node in realization.nodes if node.name == "misp")
    assert misp.image.policy_rule == "backend-open-profile"
    assert set(misp.backend_selected_concerns) == {
        "compute-substrate",
        "published-ports",
        "runtime-environment",
    }
    # ...base-container-materialized nodes are realized by the generic materializer, not here.
    assert "webapp" not in services
    assert "workstation" not in services
    ad = next(node for node in realization.nodes if node.name == "ad")
    assert ad.backend_base_image_ref == "aptl/generic-samba-ad-wazuh-agent-base:latest"
    assert ad.backend_base_use_image_command is True
    assert ad.backend_run_capabilities == ()
    assert ad.backend_provider_kind == "samba-active-directory"
    assert dict(ad.backend_provider_parameters) == {
        "domain": "TECHVAULT",
        "realm": "TECHVAULT.LOCAL",
    }
    webapp = next(node for node in realization.nodes if node.name == "webapp")
    assert webapp.backend_provider_kind == "python-flask-application"
    assert dict(webapp.backend_provider_parameters) == {
        "application_id": "techvault-portal",
        "module": "app:app",
        "port": "8080",
        "workdir": "/app",
    }
    assert webapp.backend_selected_concerns == ("compute-substrate",)

    # Networks use the aptl-<stem> keys and carry ipam from the SDL.
    networks = document["networks"]
    assert "aptl-security" in networks
    assert networks["aptl-security"]["ipam"]["config"][0]["subnet"] == "172.20.0.0/24"
    assert networks["aptl-dmz"]["internal"] is True

    # Wazuh's certificates and appliance clients use canonical dotted DNS
    # identities even though the backend-neutral node ids use hyphens.
    assert services["wazuh-indexer"]["networks"]["aptl-security"]["aliases"] == [
        "wazuh.indexer"
    ]
    assert services["wazuh-manager"]["networks"]["aptl-security"]["aliases"] == [
        "wazuh.manager"
    ]
    assert services["wazuh-manager"]["environment"]["INDEXER_URL"] == (
        "https://wazuh.indexer:9200"
    )
    assert services["wazuh-dashboard"]["environment"]["WAZUH_API_URL"] == (
        "https://wazuh.manager"
    )

    # depends_on never references a service the document does not define.
    defined = set(services)
    # Every dependency comes from the admitted scenario graph; plain lab start
    # does not insert a mediation service around declared Docker authority.
    external_dependencies: set[str] = set()
    for service in services.values():
        for dependency in service.get("depends_on", []):
            if dependency not in defined:
                external_dependencies.add(dependency)
    assert external_dependencies == set()

    # The released 7.0.0 pack declares no case-management or analyzer node.
    assert not {"thehive", "thehive-cassandra", "thehive-es", "cortex"} & set(services)

    # The released pack leaves MISP's runtime environment open. APTL's selected
    # cache binding therefore includes and reports its minimum backing artifact;
    # it is not inferred when that concern is closed.
    artifact = next(
        item
        for item in realization.generated_artifacts
        if item.name == "misp-cache-credential"
    )
    assert artifact.address == "backend.generated-artifact.misp-cache-credential"
    assert [output.name for output in artifact.outputs] == [
        "cache-password",
        "cache-server-config",
    ]
    assert artifact.environment_consumers[0].target_address == "provision.node.misp"
    assert artifact.environment_consumers[0].environment_variable == "REDIS_PASSWORD"
    assert artifact.details() in realization.details()["generated_artifacts"]


@pytest.mark.integration
def test_orborus_docker_authority_is_admitted_only_as_the_pack_authored_it(
    techvault_realization,
):
    """Host-root Docker access is granted by the pack, never by the backend.

    Until raes-env-packs 6.1.0 (OpenRAE/env-packs#285) TechVault declared no
    Orborus authority, so the only correct behaviour was to admit none. The
    released pack now authors the control interface and the authority Shuffle
    workflow execution needs, so the contract under test flips: the admission
    must mirror exactly what was authored, and the backend must still add
    nothing of its own -- no extra mount targets, no second holder, and no
    widening of the endpoint.
    """

    realization = techvault_realization

    spec = realization.deployment_spec(sorted(realization.profiles))

    admissions = [
        admission
        for admission in spec.docker_authority_admissions
        if admission.node_address == "provision.node.shuffle-orborus"
    ]
    assert len(admissions) == 1
    admission = admissions[0]
    assert admission.engine == "docker"
    assert admission.privilege_class == "host_root_equivalent"
    assert admission.endpoint_kind == "unix_socket"
    assert admission.endpoint_target == "/var/run/docker.sock"
    assert admission.endpoint_read_write is True
    # The authority holder mounts nothing else, so no mount target is admitted
    # alongside the socket.
    assert admission.allowed_mount_targets == ()

    # The pack names two spawn templates, and this asserts they are realized as
    # authored. It is not a bound on what the holder may launch: a
    # host-root-equivalent daemon holder can pull or build anything regardless
    # of what APTL staged, so the image list is realization demand rather than
    # a gate. This pack happens to pin both templates by digest, under the
    # authority's own bounded execution deadline.
    requirements = admission.spawn_requirements
    assert len(requirements) == 2
    assert {requirement.template_id for requirement in requirements} == {
        "shuffle-worker",
        "shuffle-http-1-4-0",
    }
    for requirement in requirements:
        assert "@sha256:" in requirement.image_ref, requirement.template_id
        assert requirement.execution_timeout_seconds == 600
        # realized_children is an optional description the author may omit.
        # APTL reads nothing from it, so nothing here depends on one.
        assert requirement.tag_reference in {"", "frikky/shuffle:http_1.4.0"}

    orborus = next(node for node in realization.nodes if node.name == "shuffle-orborus")
    interfaces = orborus.runtime.local_control_interfaces
    assert [interface.control_interface_id for interface in interfaces] == [
        "docker-sock"
    ]
    authorities = orborus.runtime.orchestration_authorities
    assert [authority.orchestration_authority_id for authority in authorities] == [
        "shuffle-orborus"
    ]
    # Orborus is the only holder: no other node acquires Docker authority
    # because the pack grew one.
    assert {
        admission.node_address for admission in spec.docker_authority_admissions
    } == {"provision.node.shuffle-orborus"}


def test_base_container_consumers_are_excluded_from_the_compose_stateful_override():
    """Base-container-materialized nodes get artifacts via the materializer, not Compose mounts.

    A generated-artifact consumer on a base-container-materialized node has no Compose service to
    bind into, so including it in the stateful override makes the effective-model
    check flag a declared mount no service can carry. It must be excluded (#875).
    """

    from raes.runtime_configuration import RuntimeConfiguration

    from aptl.core.deployment._compose_stateful_model import stateful_override_payload
    from aptl.core.deployment.realization import (
        DeploymentGeneratedArtifactOutput,
        DeploymentGeneratedArtifactRealization,
        DeploymentImageRealization,
        DeploymentNodeRealization,
        DeploymentRealizationSpec,
        DeploymentStatefulConsumer,
    )

    def _consumer(node: str):
        return DeploymentStatefulConsumer(
            target_address=f"provision.node.{node}",
            node_name=node,
            service_name=node,
            mount_destination="/run/keys",
            access_mode="read_only",
            selected_outputs=("k",),
        )

    artifact = DeploymentGeneratedArtifactRealization(
        address="provision.generated.k",
        name="k",
        generator="rendered_config",
        lifecycle="regenerate_on_change",
        provenance="techvault:flag-signing-profile/v2",
        outputs=(
            DeploymentGeneratedArtifactOutput(name="k", path="k", sensitivity="secret"),
        ),
        consumers=(_consumer("imagenode"), _consumer("freenode")),
    )
    spec = DeploymentRealizationSpec(
        profiles=(),
        nodes=(
            DeploymentNodeRealization(
                address="provision.node.imagenode",
                name="imagenode",
                service_name="imagenode",
                container_name="aptl-imagenode",
                networks=(),
            ),
            DeploymentNodeRealization(
                address="provision.node.freenode",
                name="freenode",
                service_name="freenode",
                container_name="aptl-freenode",
                networks=(),
                runtime=RuntimeConfiguration(),
            ),
        ),
        networks=(),
        images=(
            DeploymentImageRealization(
                address="provision.node.imagenode",
                service_name="imagenode",
                source_name="x",
                source_version="1",
                image_ref="x:1",
                mode="pull",
                policy_rule="allowed-source",
            ),
        ),
        generated_artifacts=(artifact,),
    )

    services = stateful_override_payload(Path("/tmp"), "proj", spec)["services"]
    assert "imagenode" in services  # image node keeps its Compose mount
    assert "freenode" not in services  # base-container-materialized node does not


@pytest.mark.integration
def test_base_os_nodes_use_the_released_base_container_materialization(
    techvault_realization,
):
    """The 6.0 pack declares these nodes as state, not APTL component builds."""

    realization = techvault_realization
    by_name = {node.address.rsplit(".", 1)[-1]: node for node in realization.nodes}

    for name in ("ad", "db", "webapp", "workstation", "kali"):
        node = by_name[name]
        assert node.image is None
        assert node.runtime is not None
        assert node.os == "linux"
