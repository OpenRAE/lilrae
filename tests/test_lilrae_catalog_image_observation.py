"""Read back catalog image identity through the actual container, fail closed."""

import json
from subprocess import CompletedProcess
from unittest.mock import MagicMock

import pytest

from aptl.core.deployment._compose_image_realization import ComposeRealizationImageMixin
from aptl.core.deployment._docker_image_identity import EXACT_IMAGE_INSPECT_FORMAT

PIN = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64
CONFIG = "sha256:" + "c" * 64
REF = "docker.io/library/postgres@" + PIN


class Backend(ComposeRealizationImageMixin):
    def __init__(self, references, *, config=CONFIG, image_config=CONFIG):
        def run(argv, **kwargs):
            if argv[:2] == ["docker", "inspect"]:
                output = config
            elif argv[:3] == ["docker", "image", "inspect"]:
                assert argv[argv.index("--format") + 1] == EXACT_IMAGE_INSPECT_FORMAT
                assert argv[-1] == config
                output = json.dumps(references) + "\t" + image_config + "\tlinux/amd64"
            else:
                raise AssertionError(argv)
            return CompletedProcess(argv, 0, output, "")

        self._run = MagicMock(side_effect=run)


def test_readback_correlates_selected_pin_regardless_of_alias_order():
    backend = Backend(["other/image@" + OTHER, "postgres@" + PIN])
    assert backend.container_image_digest("owned-container", expected_ref=REF) == PIN
    assert all("pull" not in call.args[0] for call in backend._run.call_args_list)


@pytest.mark.parametrize(
    "refs,config,image_config",
    [
        (["postgres@" + OTHER], CONFIG, CONFIG),
        (["other/image@" + PIN], CONFIG, CONFIG),
        ([], CONFIG, CONFIG),
        (["postgres@" + PIN], CONFIG, OTHER),
        (["postgres@" + PIN], "not-a-digest", CONFIG),
    ],
)
def test_readback_rejects_unproven_identity(refs, config, image_config):
    backend = Backend(refs, config=config, image_config=image_config)
    assert backend.container_image_digest("owned-container", expected_ref=REF) is None


def _catalog_realization():
    from aptl.backends.raes_realization_model import AptlRealization, NodeRealization
    from aptl.core.deployment.realization import DeploymentImageRealization

    image = DeploymentImageRealization(
        address="provision.node.arbitrary",
        service_name="arbitrary",
        source_name="postgresql",
        source_version="17",
        image_ref=REF,
        mode="pull",
        policy_rule="trusted-source-catalog",
        catalog_record="postgresql-17",
        provenance_refs=("https://example.test/reviewed-pin",),
    )
    node = NodeRealization(
        address=image.address,
        name="arbitrary",
        aliases=(),
        profiles=(),
        backend_services=("arbitrary",),
        container_name="owned-container",
        services=(),
        networks=(),
        static_addresses=(),
        image=image,
    )
    return AptlRealization(
        profiles=frozenset(), nodes=(node,), networks=(), placements=(), diagnostics=()
    )


@pytest.mark.parametrize("verified", [True, False])
@pytest.mark.parametrize("container_ready", [True, False])
def test_observation_records_source_selection_and_independent_readback(
    tmp_path, monkeypatch, verified, container_ready
):
    from aptl.backends import raes_observation as observation
    from aptl.backends._raes_observation_helpers import ObservedResource
    from raes_contracts.planning import ProvisioningPlan, PlannedResource, RuntimeDomain

    realization = _catalog_realization()
    node = realization.nodes[0]
    resource = PlannedResource(
        address=node.address,
        domain=RuntimeDomain.PROVISIONING,
        resource_type="node",
        payload={},
    )
    plan = ProvisioningPlan(resources={node.address: resource}, operations=[])
    backend = MagicMock()
    backend.project_name = "test"
    backend.container_image_digest.return_value = PIN if verified else None
    backend.container_image_config_id.return_value = CONFIG
    monkeypatch.setattr(
        observation,
        "_observe_planned_resource",
        lambda *args: ObservedResource(realized=container_ready),
    )
    observed = observation.observe_realization(backend, realization, plan, tmp_path)[
        node.address
    ]
    assert observed.realized is (verified and container_ready)
    evidence = observed.evidence["source_image"]
    assert evidence["declared_source"] == {"name": "postgresql", "version": "17"}
    assert evidence["selected_digest"] == PIN
    assert evidence["observed_config_digest"] == CONFIG
    assert evidence["verified_manifest_digest"] == (
        PIN if verified and container_ready else None
    )
    backend.container_image_digest.assert_called_once_with(
        "owned-container", expected_ref=REF, expected_config_id=CONFIG
    )
    # Failed identity observation must also survive the report projection.
    assert (
        observation.observation_evidence({node.address: observed})[node.address][
            "source_image"
        ]
        == evidence
    )


def test_container_change_between_identity_reads_cannot_mix_digest_domains():
    from aptl.backends._lilrae_catalog_image_observation import observe_catalog_images
    from aptl.backends._raes_observation_helpers import ObservedResource

    backend = Backend(["postgres@" + PIN], config=OTHER, image_config=OTHER)
    # The initial read preceded an external container replacement. The later
    # image inspection must not attribute that pin to the earlier config ID.
    run = backend._run
    first_read = True

    def changing_container(argv, **kwargs):
        nonlocal first_read
        if first_read and argv[:2] == ["docker", "inspect"]:
            first_read = False
            return CompletedProcess(argv, 0, CONFIG, "")
        return run(argv, **kwargs)

    backend._run = changing_container
    realization = _catalog_realization()
    address = realization.nodes[0].address
    observations = {address: ObservedResource(realized=True)}
    observe_catalog_images(backend, realization, observations)
    assert not observations[address].realized


def test_malformed_completed_config_cannot_verify_a_catalog_image():
    from aptl.backends._lilrae_catalog_image_observation import observe_catalog_images
    from aptl.backends._raes_observation_helpers import ObservedResource
    from aptl.core.deployment.observation import (
        CompletedContainerReceipt,
        DeploymentObservationContext,
    )

    backend = MagicMock()
    backend.container_image_config_id.return_value = None
    backend.container_inspect.return_value = {}
    context = DeploymentObservationContext()
    context.record_completed_autoremove(
        "owned-container",
        CompletedContainerReceipt(
            inspect={},
            image_digest=PIN,
            image_config_id="not-a-config-digest",
            selected_image_ref=REF,
        ),
    )
    realization = _catalog_realization()
    address = realization.nodes[0].address
    observations = {address: ObservedResource(realized=True)}
    observe_catalog_images(backend, realization, observations, context)
    assert not observations[address].realized
    assert (
        observations[address].evidence["source_image"]["observed_config_digest"] is None
    )


@pytest.mark.parametrize("matching_pin", [True, False])
def test_catalog_completion_receipt_verifies_pin_before_container_removal(
    tmp_path, monkeypatch, matching_pin
):
    from dataclasses import replace
    from aptl.backends import raes_observation as observation
    from aptl.core.deployment.docker_compose import DockerComposeBackend
    from aptl.core.deployment.observation import DeploymentObservationContext
    from tests.test_compose_autoremove import _spec, _completed_inspect
    from raes_contracts.planning import ProvisioningPlan, PlannedResource, RuntimeDomain

    realization = _catalog_realization()
    node = realization.nodes[0]
    spec = _spec()
    node = replace(node, runtime=spec.nodes[0].runtime)
    realization = replace(realization, nodes=(node,))
    spec = replace(
        spec,
        nodes=(
            replace(
                spec.nodes[0], address=node.address, container_name=node.container_name
            ),
        ),
        images=(node.image,),
    )
    backend = DockerComposeBackend(tmp_path, project_name="test")
    context = DeploymentObservationContext()
    present = True

    def run(argv, **kwargs):
        nonlocal present
        if argv[:2] == ["docker", "rm"]:
            assert matching_pin
            present = False
            output = ""
        elif argv[:2] == ["docker", "inspect"]:
            assert present
            output = CONFIG
        elif argv[:3] == ["docker", "image", "inspect"]:
            assert present
            # An unrelated first alias must not determine completion proof.
            refs = [
                "other/image@" + OTHER,
                "postgres@" + (PIN if matching_pin else OTHER),
            ]
            output = json.dumps(refs)
            if argv[argv.index("--format") + 1] == EXACT_IMAGE_INSPECT_FORMAT:
                output += "\t" + CONFIG + "\tlinux/amd64"
        else:
            raise AssertionError(argv)
        return CompletedProcess(argv, 0, output, "")

    monkeypatch.setattr(backend, "_run", run)
    monkeypatch.setattr(backend, "container_exists", lambda name: present)
    monkeypatch.setattr(
        backend,
        "container_inspect",
        lambda name: _completed_inspect() if present else {},
    )
    monkeypatch.setattr(
        backend, "container_file_read", lambda *args, **kwargs: b"ID=debian\n"
    )
    monkeypatch.setattr(backend, "host_list_lab_networks", lambda project: [])
    monkeypatch.setattr(backend, "_resolve_owned_container_id", lambda name: name)
    failures = backend._retire_completed_autoremove_nodes(spec, context)
    if not matching_pin:
        assert failures
        assert present
        assert not context.autoremove_verified(node.container_name)
        return
    assert not failures
    assert not present
    assert context.autoremove_verified(node.container_name)
    monkeypatch.setattr(backend, "container_image_config_id", lambda name: None)
    monkeypatch.setattr(backend, "container_image_digest", lambda *args, **kwargs: None)
    resource = PlannedResource(
        address=node.address,
        domain=RuntimeDomain.PROVISIONING,
        resource_type="node",
        payload={},
    )
    plan = ProvisioningPlan(resources={node.address: resource}, operations=[])
    # The ordinary observer also consumes the real successful-removal context.
    observed = observation.observe_realization(
        backend, realization, plan, tmp_path, observation_context=context
    )[node.address]
    assert observed.realized
    assert observed.evidence["source_image"]["observed_config_digest"] == CONFIG
    assert observed.evidence["source_image"]["verified_manifest_digest"] == PIN
    # A reappearing container must be verified live, never hidden by a receipt.
    monkeypatch.setattr(backend, "container_inspect", lambda name: _completed_inspect())
    for live_config in (OTHER, None):
        monkeypatch.setattr(
            backend, "container_image_config_id", lambda name: live_config
        )
        replaced = observation.observe_realization(
            backend, realization, plan, tmp_path, observation_context=context
        )[node.address]
        assert not replaced.realized
    monkeypatch.setattr(backend, "container_inspect", lambda name: {})
    monkeypatch.setattr(backend, "container_image_config_id", lambda name: None)
    # A receipt proves only the pin selected and inspected before removal.
    changed = replace(
        realization,
        nodes=(
            replace(node, image=replace(node.image, image_ref="postgres@" + OTHER)),
        ),
    )
    rejected = observation.observe_realization(
        backend, changed, plan, tmp_path, observation_context=context
    )[node.address]
    assert not rejected.realized


def test_compaction_preserves_source_image_evidence():
    from aptl.backends._raes_apply_reporting import bounded_apply_details

    evidence = {
        "declared_source": {"name": "postgresql", "version": "17"},
        "selected_digest": PIN,
        "observed_config_digest": CONFIG,
    }
    details = bounded_apply_details(
        {
            "realization": {"large": "x" * 70_000},
            "observation_evidence": {
                "provision.node.arbitrary": {"source_image": evidence}
            },
        },
        _catalog_realization(),
    )
    assert details["source_image_evidence"] == {"provision.node.arbitrary": evidence}


def test_verified_source_evidence_survives_in_the_portable_snapshot():
    from aptl.backends._raes_observation_helpers import ObservedResource
    from aptl.backends.raes_diagnostics import snapshot_after_apply
    from raes_contracts.planning import ProvisioningPlan, PlannedResource, RuntimeDomain
    from raes_contracts.runtime_state import RuntimeSnapshot
    from aptl.backends.raes_repro import runtime_snapshot_record_payload

    address = "provision.node.arbitrary"
    resource = PlannedResource(
        address=address,
        domain=RuntimeDomain.PROVISIONING,
        resource_type="node",
        payload={},
    )
    plan = ProvisioningPlan(resources={address: resource}, operations=[])
    evidence = {
        "declared_source": {"name": "postgresql", "version": "17"},
        "selected_digest": PIN,
        "observed_config_digest": CONFIG,
    }
    observed = ObservedResource(realized=True, evidence={"source_image": evidence})
    snapshot = snapshot_after_apply(plan, RuntimeSnapshot(), {address: observed})
    archived = runtime_snapshot_record_payload(snapshot)
    assert (
        archived["entries"][address]["payload"]["backend_evidence"]["source_image"]
        == evidence
    )


def test_unverified_catalog_image_does_not_advance_apply_snapshot(
    tmp_path, monkeypatch
):
    from aptl.backends import raes_observation as observation
    from aptl.backends import _raes_provisioner_start as start
    from aptl.backends._raes_observation_helpers import ObservedResource
    from aptl.core.deployment.observation import DeploymentObservationContext
    from raes_contracts.runtime_state import RuntimeSnapshot
    from tests.test_lilrae_source_image_catalog import _provisioner_plan

    provisioner, plan = _provisioner_plan(tmp_path)
    backend = provisioner.deployment_backend
    backend.project_name = "test"
    backend.container_image_digest.return_value = None
    backend.container_image_config_id.return_value = CONFIG
    monkeypatch.setattr(
        provisioner,
        "_start_and_observe_apparatus",
        lambda *args: (DeploymentObservationContext(), ()),
    )
    monkeypatch.setattr(
        provisioner, "_compose_validity_diagnostics", lambda *args, **kwargs: []
    )
    monkeypatch.setattr(start, "_boundary_admission_failed", lambda *args: False)
    monkeypatch.setattr(
        observation,
        "_observe_planned_resource",
        lambda *args: ObservedResource(realized=True),
    )
    baseline = RuntimeSnapshot()
    result = provisioner.apply(plan, baseline)
    assert not result.success
    assert result.snapshot == baseline
    assert any("catalog-image-unverified" in d.message for d in result.diagnostics)
    assert (
        result.details["observation_evidence"]["provision.node.arbitrary"][
            "source_image"
        ]["verified_manifest_digest"]
        is None
    )
    assert (
        provisioner.last_source_image_evidence["provision.node.arbitrary"][
            "observed_config_digest"
        ]
        == CONFIG
    )


def test_failed_source_evidence_reaches_the_run_outcome(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from aptl.backends import raes
    from aptl.core.lab_types import LabResult
    from raes_contracts.runtime_state import RuntimeSnapshot
    from tests.test_lilrae_source_image_catalog import _provisioner_plan

    provisioner, plan = _provisioner_plan(tmp_path)
    evidence = {
        "provision.node.arbitrary": {
            "selected_digest": PIN,
            "observed_config_digest": CONFIG,
            "verified": False,
        }
    }

    def failed_apply(*args, **kwargs):
        provisioner.last_source_image_evidence = evidence
        return (
            LabResult(success=False, error="catalog-image-unverified"),
            RuntimeSnapshot(),
            False,
            None,
        )

    monkeypatch.setattr(raes, "_apply_execution_plan", failed_apply)
    target = SimpleNamespace(provisioner=provisioner, participant_runtime=None)
    execution_plan = SimpleNamespace(provisioning=plan, diagnostics=[])
    outcome = raes._run_execution_plan(target, execution_plan)
    assert not outcome.lab_result.success
    assert outcome.realization_details["source_image_evidence"] == evidence
