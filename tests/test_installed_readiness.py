"""Readiness uses native owners; only the external process transport is scripted."""

import json
import platform
from dataclasses import replace

import pytest
from raes_processor.trial_realization import realize_admitted_trial_entry
from raes_runtime.registry import RuntimeTarget

from aptl.backends.installed_readiness import InstalledReadiness
from aptl.backends.raes_evaluator import AptlEvaluator
from aptl.backends.raes_orchestrator import AptlOrchestrator
from aptl.backends.raes_participant_runtime import AptlParticipantRuntime
from aptl.backends.raes_provisioner import AptlProvisioner
from aptl.core.config import AptlConfig
from aptl.core.correlation.clock import FixedClockProvider
from aptl.core.deployment.docker_compose import DockerComposeBackend
from aptl.core.evidence.adapters.builtins import soc_windowed_source
from aptl.core.evidence.adapters.sources import WindowedQueryCollector
from aptl.core.execution_boundary import capture_execution_boundary
from aptl.core.experiment.capture_registry import CollectorRegistry
from aptl.core.scenario_bundle import project_tree_bundle
from aptl.utils.curl_safe import curl_json
from aptl.utils.probe_execution import bounded_probe_commands
from aptl.workbench.process import ProcessCleanup, ProcessResult
from tests.cleanup_runtime_fixture import Services, runtime_inputs


def native_apparatus(context):
    from raes_backend_protocols.manifest import (
        backend_manifest_from_v2_model_with_envelope,
    )
    from raes_contracts.canonical import canonical_json_digest
    from raes_contracts.contracts import (
        ExperimentBackendReferenceModel,
        ExperimentProcessorReferenceModel,
    )
    from raes_processor.manifest import reference_processor_manifest_v2_model

    from aptl.backends.cleanup import CLEANUP_CAPABILITIES
    from aptl.backends.raes_manifest import (
        create_aptl_binding_manifest_model,
        create_aptl_manifest,
        create_aptl_realization_envelope,
    )
    from tests.structural_family_fixture import _manifest_ref
    from tests.test_experiment_capture_mapping import _covering_registration

    original = next(
        value
        for key, value in context["apparatus_manifests"].items()
        if key[0] == "backend"
    )
    runtime = backend_manifest_from_v2_model_with_envelope(
        original, context["realization_envelope"]
    )
    registry = CollectorRegistry(
        (_covering_registration(capture_offer=runtime.observation.capture_offers[0]),)
    )
    backend = create_aptl_binding_manifest_model(
        create_aptl_manifest(registry, cleanup=CLEANUP_CAPABILITIES)
    )
    processor = reference_processor_manifest_v2_model(compatible_backends=["aptl"])
    envelope = create_aptl_realization_envelope()
    manifests = {}
    for key, manifest in context["participant_manifests"].items():
        payload = manifest.model_dump(mode="json")
        payload["compatibility"]["backends"] = ["aptl"]
        payload["compatibility"]["participant_runtimes"] = ["aptl"]
        manifests[key] = type(manifest).model_validate(payload)
    context["participant_manifests"] = manifests
    context["apparatus_manifests"] = {
        (
            "backend",
            backend.identity.name,
            backend.identity.version,
            backend.schema_version,
        ): backend,
        (
            "processor",
            processor.identity.name,
            processor.identity.version,
            processor.schema_version,
        ): processor,
    }
    context["realization_envelope"] = envelope
    context["apparatus"] = context["apparatus"].model_copy(
        update={
            "manifest_refs": [
                _manifest_ref(backend, "backend", ExperimentBackendReferenceModel),
                _manifest_ref(
                    processor, "processor", ExperimentProcessorReferenceModel
                ),
            ],
            "realization_envelope": envelope.identity,
            "participant_manifest_refs": [
                ref.model_copy(
                    update={
                        "manifest_digest": canonical_json_digest(
                            manifests[
                                next(
                                    key
                                    for key in manifests
                                    if key[0] == ref.participant_address
                                )
                            ].model_dump(mode="json")
                        )
                    }
                )
                for ref in context["apparatus"].participant_manifest_refs
            ],
        }
    )
    return context


def test_native_control_only_plan_passes_public_runtime_admission(tmp_path):
    """The native baseline must reach the installed runtime without a matrix."""
    from raes_runtime import RuntimeControlPlane

    inputs, manifest = runtime_inputs(
        tmp_path,
        control_only=True,
        native_runtime=True,
        apparatus_transform=native_apparatus,
    )
    backend = DockerComposeBackend(tmp_path)
    target = RuntimeTarget(
        name=manifest.name,
        manifest=manifest,
        provisioner=AptlProvisioner(
            tmp_path,
            AptlConfig(),
            backend,
            project_tree_bundle(
                tmp_path, next((tmp_path / "pack").rglob("*.sdl.yaml"))
            ),
        ),
        orchestrator=AptlOrchestrator(),
        evaluator=AptlEvaluator(),
        participant_runtime=AptlParticipantRuntime(deployment_backend=backend),
    )
    with RuntimeControlPlane(target) as runtime:
        assert runtime.admit_experiment(inputs, services=Services(tmp_path))


class NativeTransport:
    def __init__(self):
        self.calls = []
        self.daemon = "approved-daemon"
        self.source_available = True
        self.map_count = 262144
        self.containers = {}

    def run(self, argv, **options):
        self.calls.append(tuple(argv))
        assert options["max_output_bytes"] <= 65536
        if argv[:3] == ("docker", "context", "inspect"):
            output = json.dumps("unix:///var/run/docker.sock")
        elif argv[:2] == ("docker", "info"):
            output = (
                self.daemon
                if "{{.ID}}" in argv
                else json.dumps(
                    {
                        "ID": self.daemon,
                        "OSType": "linux",
                        "OperatingSystem": "Linux",
                        "KernelVersion": platform.release(),
                        "ServerVersion": "29.5.0",
                    }
                )
            )
        elif argv[0] == "sysctl":
            output = f"vm.max_map_count = {self.map_count}"
        elif argv[0] == "curl" and any("openrouter.ai" in item for item in argv):
            from tests.test_provider_readiness import ProviderRunner

            return ProviderRunner(None if self.source_available else "transport").run(
                argv, **options
            )
        elif argv[0] == "curl":
            return ProcessResult(
                0 if self.source_available else 7, b"[]", b"", ProcessCleanup(1, 0)
            )
        elif argv[:2] == ("docker", "inspect"):
            output = json.dumps([self.containers[argv[-1]]])
        elif argv[:2] == ("docker", "ps") or argv[:3] in {
            ("docker", "volume", "ls"),
            ("docker", "network", "ls"),
        }:
            output = ""
        elif argv == ("fixture-agent", "--version"):
            output = "2.0.0"
        elif argv[-1] == "--version":
            output = "1.19.5"
        else:
            raise AssertionError(argv)
        return ProcessResult(0, output.encode(), b"", ProcessCleanup(1, 0))


@pytest.fixture
def installed(tmp_path):
    from pathlib import Path

    from aptl.backends.lilrae_participant_configuration import (
        configured_opencode_executor,
    )
    from aptl.core.runstore import LocalRunStore
    from tests.opencode_fixture import synthetic_options
    from tests.test_lilrae_participant_configuration import configuration

    transport = NativeTransport()
    backend = DockerComposeBackend(tmp_path)
    clock = FixedClockProvider(measurement_time="2026-11-01T10:00:00Z")
    store = LocalRunStore(tmp_path / "runs")
    store.base_dir.mkdir()
    manifest, result = configuration()
    executor = configured_opencode_executor(
        configuration=result,
        manifest=manifest,
        prompt="red task",
        prompt_ref="content.red-prompt@v1",
        supported_models=frozenset({"openrouter/model"}),
        options=synthetic_options(
            executable=Path("/bin/true"),
            work_root=tmp_path,
            runner=transport,
            environment={"OPENROUTER_API_KEY": "synthetic-key"},
        ),
    )
    collector = WindowedQueryCollector(
        "approved.source",
        soc_windowed_source(
            lambda start, end: curl_json("https://approved.invalid"),
            readiness=lambda at: curl_json("https://approved.invalid") == [],
        ),
    )
    with bounded_probe_commands(transport, 65536):
        approved = capture_execution_boundary(backend)
    from aptl.core.placement_readiness import AppliancePlacementReadiness
    from tests.test_appliance_boundary_inventory import _binding, _guest, _host, _policy

    binding = _binding().model_copy(update={"guest_daemon_id": transport.daemon})
    guest = _guest().model_copy(update={"guest_daemon_id": transport.daemon})
    containment = AppliancePlacementReadiness(_policy(), binding, _host, lambda: guest)
    return InstalledReadiness(
        backend,
        approved,
        (executor.readiness_owner(manifest),),
        {collector.registration_id: collector},
        store,
        clock,
        transport,
        containment=containment,
    ), transport


def test_concrete_owners_prove_build_provider_source_writer_and_exact_resource_demand(
    installed,
):
    installed, transport = installed
    with bounded_probe_commands(transport, 65536):
        owners = installed.owners()
        assert owners.containment()
        assert owners.participants[0].check()
        assert owners.captures["approved.source"].check(None)
        assert owners.captures["approved.source"].destination.check(1024)
        assert owners.resources(None, 262144)
        transport.map_count = 262143
        assert not owners.resources(None, 262144)
        transport.source_available = False
        assert not owners.participants[0].check()
        assert not owners.captures["approved.source"].check(None)
        transport.daemon = "changed-daemon"
        assert not owners.containment()
    assert not list((installed.store.base_dir / ".readiness").iterdir())


@pytest.mark.parametrize(
    "failure", ["absent", "host-missing", "perimeter-failed", "daemon-mismatch"]
)
def test_matching_daemon_cannot_replace_positive_containment_proof(installed, failure):
    installed, transport = installed
    proof = installed.containment
    if failure == "absent":
        proof = None
    elif failure == "host-missing":
        proof = replace(proof, host=lambda: None)
    elif failure == "perimeter-failed":
        host = proof.host().model_copy(update={"forbidden_reachability_passed": False})
        proof = replace(proof, host=lambda: host)
    else:
        guest = proof.guest().model_copy(update={"guest_daemon_id": "different"})
        proof = replace(proof, guest=lambda: guest)
    installed = replace(installed, containment=proof)
    with bounded_probe_commands(transport, 65536):
        assert not installed.containment_ready()


def test_native_contract_mismatch_is_retained_and_blocks_preparation(
    tmp_path, installed, monkeypatch
):
    from raes_contracts.trial_unit import TrialUnitRequest
    from raes_processor.planner import realization_authority_diagnostics

    installed, transport = installed
    inputs, manifest = runtime_inputs(
        tmp_path,
        control_only=True,
        native_runtime=True,
        apparatus_transform=native_apparatus,
    )
    backend = installed.backend
    target = RuntimeTarget(
        name=manifest.name,
        manifest=manifest,
        provisioner=AptlProvisioner(
            tmp_path,
            AptlConfig(),
            backend,
            project_tree_bundle(
                tmp_path, next((tmp_path / "pack").rglob("*.sdl.yaml"))
            ),
        ),
        orchestrator=AptlOrchestrator(),
        evaluator=AptlEvaluator(),
        participant_runtime=AptlParticipantRuntime(deployment_backend=backend),
    )
    entry_id = next(iter(inputs.plan.entries))
    public = realize_admitted_trial_entry(
        inputs=inputs, plan_entry_id=entry_id, target_name=target.name
    )
    assert not realization_authority_diagnostics(
        public.execution_plan.provisioning, manifest
    )
    from aptl.core.lab_types import LabResult

    monkeypatch.setattr(
        backend,
        "qualify_runtime_materialization",
        lambda *args, **kwargs: LabResult(success=False),
    )
    request = TrialUnitRequest(
        inputs.plan,
        entry_id,
        "native-readiness-attempt",
        public.snapshot_digest,
        public.provisioning_plan,
        public.orchestration_plan,
        public.evaluation_plan,
    )
    services = Services(tmp_path)
    services.admit(request)
    cleanup = services.cleanups[request.execution_attempt_id]
    installed = replace(installed, store=cleanup.store)
    registry = CollectorRegistry(())
    gate = installed.create_gate(inputs, target, tmp_path / "pack", registry)
    try:
        from aptl.backends.scenario_startup import (
            ScenarioStartupPlan,
            ScenarioStartupSelection,
        )

        target.provisioner.startup_selection = ScenarioStartupSelection(
            None, None, ScenarioStartupPlan("", (), (), minimum_max_map_count=262144)
        )
        gate.owners = replace(gate.owners, resources=None)
        with pytest.raises(ValueError, match="^trial-readiness-blocked$"):
            gate.prepare(request)
        checks = [
            check
            for ref in gate.references
            for check in cleanup.store.read_run_json(request.run_id, ref)["checks"]
        ]
        assert any(
            check["code"] == "lilrae.readiness.installed-backend.failed"
            for check in checks
        )
        assert any(
            check["code"] == "lilrae.readiness.resource-selection.failed"
            for check in checks
        )
        assert not gate.execution_ready
    finally:
        gate.close()


@pytest.mark.parametrize("available,outcome", [(True, "succeeded"), (False, "failed")])
def test_composed_source_readiness_controls_real_trial_delivery(
    tmp_path, installed, available, outcome
):
    from tests.test_trial_serving import finish, serving

    installed, transport = installed
    root = tmp_path / "trial"
    root.mkdir()
    with serving(root, readiness_options={"process_runner": transport}) as (
        handler,
        request,
        *_,
    ):
        registration = handler.readiness.registry.registrations[0]
        collector = WindowedQueryCollector(
            registration.registration_id,
            soc_windowed_source(
                lambda start, end: curl_json("https://approved.invalid"),
                readiness=lambda at: curl_json("https://approved.invalid") == [],
            ),
        )
        installed = replace(
            installed,
            store=handler.cleanup.store,
            collectors={collector.registration_id: collector},
        )
        owners = installed.owners()
        handler.readiness.owners = replace(
            handler.readiness.owners,
            target_identity=owners.target_identity,
            containment=owners.containment,
            captures=owners.captures,
            resources=owners.resources,
        )
        transport.source_available = available
        result = finish(handler, request)
        assert result.cleanup_receipt.trial_outcome == outcome
        assert any(call[0] == "curl" for call in transport.calls)
        assert bool(handler.readiness.execution_ready) is available


@pytest.mark.parametrize("failure", [None, "source", "service", "containment"])
def test_native_control_readiness_uses_the_installed_owners(
    tmp_path, installed, failure
):
    from hashlib import sha256

    from raes_runtime import RuntimeControlPlane

    from aptl.backends.trial_serving import DockerTrialPlacement
    from aptl.core.deployment._compose_resource_ownership import ResourceReceipt
    from aptl.core.trial_readiness import ParticipantReadiness
    from aptl.utils.probe_execution import run_bounded_probe_command
    from tests.test_experiment_capture_mapping import _covering_registration
    from tests.test_trial_serving import SchedulerDelivery

    installed, transport = installed
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  fileshare:\n    image: example.invalid/baseline@sha256:"
        + "1" * 64
        + "\n    container_name: aptl-gateway\n    profiles: [baseline]\n"
        "    volumes: [fileshare_data:/data]\nvolumes:\n  fileshare_data: {}\n"
    )
    inputs, manifest = runtime_inputs(
        tmp_path,
        control_only=True,
        native_runtime=True,
        apparatus_transform=native_apparatus,
    )
    backend = installed.backend
    provisioner = AptlProvisioner(
        tmp_path,
        AptlConfig(containers={"profiles": ["baseline"]}),
        backend,
        project_tree_bundle(tmp_path, next((tmp_path / "pack").rglob("*.sdl.yaml"))),
    )
    target = RuntimeTarget(
        name=manifest.name,
        manifest=manifest,
        provisioner=provisioner,
        orchestrator=AptlOrchestrator(),
        evaluator=AptlEvaluator(),
        participant_runtime=AptlParticipantRuntime(deployment_backend=backend),
    )
    services = Services(tmp_path)
    with RuntimeControlPlane(target) as runtime:
        experiment_id = runtime.admit_experiment(inputs, services=services)
        request = SchedulerDelivery(runtime, experiment_id).request
        cleanup = services.cleanups[request.execution_attempt_id]
        registration = _covering_registration(
            capture_offer=manifest.observation.capture_offers[0]
        )
        collector = WindowedQueryCollector(
            registration.registration_id,
            soc_windowed_source(
                lambda start, end: curl_json("https://approved.invalid"),
                readiness=lambda at: curl_json("https://approved.invalid") == [],
            ),
        )

        def participant_ready():
            build = run_bounded_probe_command(
                ["fixture-agent", "--version"], cwd=tmp_path, timeout=1
            )
            return (
                build is not None
                and build.returncode == 0
                and build.stdout == "2.0.0"
                and curl_json("https://approved.invalid") == []
            )

        participants = tuple(
            ParticipantReadiness(
                implementation,
                lambda configuration=configuration: configuration.model_copy(deep=True),
                participant_ready,
            )
            for configuration in request.participant_configurations
            for key, implementation in inputs.participant_manifests.items()
            if key[0] == configuration.participant_address
        )
        native = replace(
            installed,
            store=cleanup.store,
            participants=participants,
            collectors={collector.registration_id: collector},
            containment=None if failure == "containment" else installed.containment,
        )
        gate = native.create_gate(
            inputs, target, tmp_path / "pack", CollectorRegistry((registration,))
        )
        try:
            from raes_contracts.runtime_state import RuntimeSnapshot

            # Direct native calls cannot bypass the wrapper's preparation.
            with pytest.raises(ValueError, match="^trial-readiness-not-prepared$"):
                provisioner.apply(request.provisioning_plan, RuntimeSnapshot())
            gate.record_clean(
                request, DockerTrialPlacement(backend, tmp_path).require_clean
            )
            if failure == "containment":
                with pytest.raises(ValueError, match="^trial-readiness-blocked$"):
                    gate.prepare(request)
                return
            realized = realize_admitted_trial_entry(
                inputs=inputs,
                plan_entry_id=request.plan_entry_id,
                target_name=target.name,
            )
            assert not provisioner.validate(realized.execution_plan.provisioning)
            lowered = provisioner.realize_plan(realized.execution_plan.provisioning)
            spec = lowered.deployment_spec(provisioner.selected_profiles(lowered))
            with bounded_probe_commands(transport, 65536):
                qualification = backend.qualify_runtime_materialization(
                    spec, scenario_root=tmp_path / "pack"
                )
            assert qualification.success, qualification
            gate.prepare(request)
            assert any(node.container_name for node in spec.nodes)
            ownership = backend._ensure_resource_ownership()
            attempt = ownership.new_attempt_id()
            for node in spec.nodes:
                if node.container_name is None:
                    continue
                native_id = sha256(node.container_name.encode()).hexdigest()
                external = ownership.container_name(node.container_name)
                ownership.record(
                    ResourceReceipt(
                        "container",
                        native_id,
                        external,
                        node.container_name,
                        node.address,
                        ownership.workspace_id,
                        ownership.project_name,
                        transport.daemon,
                        attempt,
                    )
                )
                transport.containers[native_id] = {
                    "Id": native_id,
                    "Name": "/" + external,
                    "Config": {"Labels": ownership.labels(attempt_id=attempt)},
                    "State": {
                        "Running": failure != "service",
                        "Health": {"Status": "healthy"},
                    },
                }
            transport.source_available = failure != "source"
            if failure:
                with pytest.raises(ValueError, match="^trial-readiness-blocked$"):
                    gate.check_live()
            else:
                gate.check_live()
            assert gate.execution_ready is (failure is None)
        finally:
            gate.close()
