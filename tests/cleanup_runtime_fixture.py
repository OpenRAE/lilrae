"""Compose the real cleanup service into the released RAE trial lifecycle.

The other installed owners are test doubles. No reference-backend package or
LilRAE scheduling loop is used.
"""

import hashlib
import json
from dataclasses import replace

import yaml
from raes import admit_scenario_family, parse_sdl
from raes.canonical import canonical_sdl_digest
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import ExperimentBackendReferenceModel
from raes_contracts.planning import ChangeAction, RuntimeDomain
from raes_contracts.realization_observation import (
    ObservedOperatingSystemIdentity,
    RealizationObservationDisclosure,
)
from raes_contracts.runtime_state import ApplyResult, SnapshotEntry
from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope
from raes_env_packs import load_pack_experiments
from raes_processor.trial_compiler import compile_admitted_trial_plan
from raes_processor.trial_realization import (
    TrialRealizationInputs,
    instantiate_admitted_trial_entry,
    realize_admitted_trial_entry,
)
from raes_runtime.registry import RuntimeTarget
from raes_runtime.runtime_trial_services import (
    TrialCaptureObservation,
    TrialConfigurationObservation,
    TrialExecutionObservation,
)

from aptl.backends.cleanup import DeclaredCleanup
from aptl.backends.raes_artifact_availability import artifact_availability_for_scenario
from aptl.backends.raes_artifact_mechanisms import (
    aptl_artifact_mechanisms,
    exact_artifact_profile,
)
from aptl.backends.raes_evaluator import AptlEvaluator
from aptl.backends.raes_orchestrator import AptlOrchestrator
from aptl.backends.raes_participant_runtime import AptlParticipantRuntime
from aptl.core.cleanup import CleanupBinding
from aptl.core.correlation.clock import FixedClockProvider
from aptl.core.runstore import LocalRunStore
from tests.structural_family_fixture import (
    FIXTURE,
    _apparatus_context,
    _manifest_ref,
    build_pack,
)
from tests.test_declared_cleanup import NativeOwner


def runtime_inputs(
    tmp_path,
    *,
    on_timeout=None,
    content_reporting=False,
    native_policy=None,
    native_bindings=(),
    control_only=False,
    required_artifact=False,
    native_runtime=False,
    apparatus_transform=None,
):
    root = build_pack(tmp_path / "pack")
    if content_reporting:
        from tests.structural_family_fixture import write_content_manifest

        path = root / "experiments/alert-capture.capture.json"
        spec = json.loads(path.read_text())
        for window in spec["capture_windows"]:
            window["starts_at"] = "2026-01-01T00:00:00Z"
            window["ends_at"] = "2099-01-01T00:00:00Z"
        path.write_text(json.dumps(spec))
        write_content_manifest(root)
    (experiment,) = load_pack_experiments(root)
    context = _apparatus_context(experiment, FIXTURE)
    if native_policy:
        from tests.trial_reporting_fixture import add_native_context

        add_native_context(context, native_bindings)
    if apparatus_transform is not None:
        context = apparatus_transform(context)
    authority = context["execution_authority"].model_dump(mode="json")
    if on_timeout is not None:
        authority["on_timeout"] = on_timeout
    authority["cleanup"]["clean_state"]["verification_probe_refs"] = [
        "native-absence:range"
    ]
    authority["cleanup"]["cleanup_obligations"]["destroy"][
        "verification_probe_refs"
    ] = ["native-absence:range"]
    context["execution_authority"] = type(
        context["execution_authority"]
    ).model_validate(authority)
    backend_key = next(
        key for key in context["apparatus_manifests"] if key[0] == "backend"
    )
    backend = context["apparatus_manifests"][backend_key]
    payload = backend.model_dump(mode="json")
    if required_artifact:
        payload["realization_support"][0]["artifact_mechanisms"] = [
            aptl_artifact_mechanisms()[0].model_dump(mode="json")
        ]
    if not native_runtime:
        payload["realization_support"][0]["observation_capabilities"][
            "compute-substrate"
        ] = {
            "verification_scope": "presence",
            "observation_strength": "guest-observed",
        }
    payload["capabilities"]["cleanup"]["supported_verification_methods"] = [
        "native-absence"
    ]
    backend = type(backend).model_validate(payload)
    context["apparatus_manifests"][backend_key] = backend
    context["apparatus"] = context["apparatus"].model_copy(
        update={
            "manifest_refs": [
                _manifest_ref(backend, "backend", ExperimentBackendReferenceModel)
                if ref.subject_ref.ref_kind == "backend"
                else ref
                for ref in context["apparatus"].manifest_refs
            ],
        }
    )
    compilation = experiment.compilation_request(**context)
    # The compiler-only fixture leaves guest identity open. This installed
    # test target independently reports Ubuntu 22.04 from its guest readback.
    family_payload = yaml.safe_load(
        (root / "sdl/structural-fixture.sdl.yaml").read_text()
    )
    if native_policy:
        from tests.trial_reporting_fixture import add_native_scenario

        add_native_scenario(family_payload, native_policy)
    for node in family_payload["nodes"].values():
        node.update(os_distribution="ubuntu", os_version="22.04", architecture="x86_64")
        node.pop("runtime", None)
        if native_runtime:
            node.pop("source", None)
            node.pop("architecture", None)
            node.pop("os_distribution", None)
            node.pop("os_version", None)
    if native_runtime:
        # Native content placement uses a path relative to the registered
        # fileshare volume; the compiler fixture's absolute guest path is not
        # a supported installed-backend materialization.
        family_payload["content"]["logging-config"]["path"] = "logging.conf"
    if required_artifact:
        profile = exact_artifact_profile()
        family_payload["nodes"]["gateway"]["source"] = {
            "name": "example/app",
            "version": "1.0",
            "artifact_requirement": {
                "requirement_id": "gateway-image",
                "explicitness": "exact",
                "exact_artifact": {
                    "artifact_id": "example/app",
                    "version": "1.0",
                    "digest": "sha256:" + "1" * 64,
                    "media_type": "application/vnd.oci.image.manifest.v1+json",
                },
                "permitted_routes": [
                    {
                        "mechanism": profile.model_dump(mode="json"),
                        "acquisition": "local-lookup",
                        "timing": "backend-preparation",
                    }
                ],
            },
        }
    for alternative in family_payload["variation_points"]["sensor-layout"][
        "alternatives"
    ].values():
        alternative.pop("inventory", None)
    family = admit_scenario_family(parse_sdl(json.dumps(family_payload)))
    compilation = compilation.with_family(family)
    design = yaml.safe_load(
        (root / "experiments/structural-design.exp.yaml").read_text()
    )
    for levels in design["factorial_design"]["level_effects"].values():
        for effect in levels.values():
            for selection in effect.get("selections", []):
                selection["scenario_family_digest"] = canonical_sdl_digest(family).value
    if control_only:
        fixed = {"bindings": [], "selections": []}
        for levels in design["factorial_design"]["level_effects"].values():
            effect = next(iter(levels.values()))
            for key in fixed:
                fixed[key].extend(effect.get(key, []))
        design["factors"] = {
            "control": {
                "name": "Fixed control",
                "factor_kind": "treatment",
                "levels": ["fixed"],
            }
        }
        design["factorial_design"] = {
            "profile": "factorial-treatments-v1",
            "factor_ids": ["control"],
            "level_effects": {"control": {"fixed": fixed}},
            "target_runs_per_condition": 1,
            "condition_bound": 1,
        }
    compilation = compilation.with_experiment(
        type(compilation.experiment).model_validate(design)
    )
    if control_only:
        descriptor_ref = compilation.input_refs.binding_descriptor_set_ref.model_copy(
            update={
                "ref_digest": canonical_json_digest(
                    compilation.experiment.binding_descriptors.model_dump(mode="json")
                ),
            }
        )
        compilation = replace(
            compilation,
            input_refs=compilation.input_refs.model_copy(
                update={"binding_descriptor_set_ref": descriptor_ref}
            ),
        )
    compiled = compile_admitted_trial_plan(compilation)
    assert compiled.plan is not None, compiled.diagnostics
    inputs = TrialRealizationInputs(
        plan=compiled.plan,
        family=compilation.family,
        experiment=compilation.experiment,
        task=compilation.task,
        capture_specs=dict(compilation.capture_specs),
        apparatus_manifests=dict(compilation.apparatus_manifests),
        realization_envelope=compilation.realization_envelope,
        backend_key=backend_key,
        participant_manifests=dict(compilation.participant_manifests),
    )
    entry_id = next(iter(inputs.plan.entries))
    availability = None
    if required_artifact:
        scenario = instantiate_admitted_trial_entry(
            plan=inputs.plan, plan_entry_id=entry_id, family=inputs.family
        )

        class Available:
            def artifact_available(self, reference, *, allow_remote):
                return True

        availability = artifact_availability_for_scenario(
            scenario, Available(), allow_remote=False
        )
    realized = realize_admitted_trial_entry(
        inputs=inputs,
        plan_entry_id=entry_id,
        artifact_availability=availability,
        target_name=backend.identity.name if native_runtime else None,
    )
    return inputs, realized.execution_plan.manifest


class Provisioner:
    readiness_requires_runner = False

    def readiness_artifacts(self, scenario, probe, root):
        from raes_contracts.contracts import ArtifactAvailabilityContext

        return (
            ArtifactAvailabilityContext()
            if probe is None
            else artifact_availability_for_scenario(
                scenario,
                probe,
                allow_remote=False,
                scenario_root=root,
                materialize=False,
            )
        )

    def readiness_contract(self, plan, root):
        return not any(item.is_error for item in self.validate(plan))

    def readiness_services(self, plan):
        return False

    def readiness_resource_minimum(self, inputs, entry):
        return None

    def __init__(self, manifest):
        self.manifest = manifest
        self.readiness = None

    def validate(self, plan):
        return []

    def apply(self, plan, snapshot):
        entries = dict(snapshot.entries)
        observations = []
        for index, operation in enumerate(plan.operations):
            if operation.action is ChangeAction.DELETE:
                entries.pop(operation.address, None)
                continue
            entries[operation.address] = SnapshotEntry(
                operation.address,
                RuntimeDomain.PROVISIONING,
                operation.resource_type,
                operation.payload,
                operation.ordering_dependencies,
                operation.refresh_dependencies,
            )
            if operation.resource_type == "node":
                observations.append(
                    RealizationObservationDisclosure(
                        address=operation.address,
                        field_path="nodes."
                        + operation.payload["node_name"]
                        + ".operating-system",
                        domain="runtime-realization",
                        requirement_kind="operating-system",
                        verification_scope=RealizationVerificationScope.PRESENCE,
                        observation_strength=ObservationStrength.GUEST_OBSERVED,
                        operating_system=ObservedOperatingSystemIdentity(
                            "linux", "ubuntu", "22.04"
                        ),
                        operation_id=plan.operation_id,
                        envelope_digest=self.manifest.realization_envelope.digest,
                        configuration_digest=self.manifest.realization_envelope.configuration.configuration_digest,
                        observer_version="cleanup-fixture/v1",
                        sequence=index,
                        binding_verified=True,
                    )
                )
                observations.append(
                    RealizationObservationDisclosure(
                        address=operation.address,
                        field_path="nodes."
                        + operation.payload["node_name"]
                        + ".realization.compute-substrate",
                        domain="runtime-realization",
                        requirement_kind="compute-substrate",
                        verification_scope=RealizationVerificationScope.PRESENCE,
                        observation_strength=ObservationStrength.GUEST_OBSERVED,
                        observed_value="virtual-machine",
                        operation_id=plan.operation_id,
                        envelope_digest=self.manifest.realization_envelope.digest,
                        configuration_digest=self.manifest.realization_envelope.configuration.configuration_digest,
                        observer_version="cleanup-fixture/v1",
                        sequence=index + 100,
                        binding_verified=True,
                    )
                )
        result = ApplyResult(
            True,
            snapshot.with_entries(
                entries,
                realization_observations=tuple(observations),
                realization_envelope=plan.realization_envelope,
            ),
            changed_addresses=[operation.address for operation in plan.operations],
        )
        return (
            self.readiness.after_provisioning(plan, result)
            if self.readiness is not None
            else result
        )


def target_for(manifest, *, native_bindings=()):
    from raes_runtime.registry import ReferenceTimeRuntime

    return RuntimeTarget(
        name=manifest.name,
        manifest=manifest,
        provisioner=Provisioner(manifest),
        orchestrator=AptlOrchestrator(),
        evaluator=AptlEvaluator(),
        participant_runtime=AptlParticipantRuntime(
            deployment_backend=None, autonomous_bindings=native_bindings
        ),
        time_runtime=ReferenceTimeRuntime() if manifest.has_time else None,
    )


class Services:
    def __init__(self, root, *, failed=False, pending=False, cleanup_fails=False):
        self.root = root
        self.failed, self.pending, self.cleanup_fails = failed, pending, cleanup_fails
        self.stopped = False
        self.events = []
        self.cleanups = {}
        self.records = {}

    def admit(self, request):
        native = NativeOwner(self.root)
        boundary = next(iter(request.cleanup_plan.resource_boundaries.values()))
        native.binding = CleanupBinding(
            request.plan_entry_id,
            request.run_id,
            request.execution_attempt_id,
            "native-"
            + hashlib.sha256(request.execution_attempt_id.encode()).hexdigest(),
            boundary.boundary_id,
            boundary.owner_ref,
            tuple(boundary.resource_refs),
            self.root,
        )
        native.fail = self.cleanup_fails
        store = LocalRunStore(self.root / "runs")
        store.create_run(request.run_id)
        self.cleanups[request.execution_attempt_id] = DeclaredCleanup(
            request.cleanup_plan,
            native,
            store,
            FixedClockProvider(measurement_time="2026-11-01T10:00:00Z"),
        )
        self.cleanups[request.execution_attempt_id].admit(request)

    def evidence(self, request, phase):
        from aptl.backends.cleanup_evidence import retain_cleanup_readback
        from aptl.core.cleanup import CleanupReadback, CleanupResourceState

        cleanup = self.cleanups[request.execution_attempt_id]
        record = retain_cleanup_readback(
            cleanup.store,
            cleanup.clock,
            cleanup.native.binding,
            phase,
            CleanupReadback((CleanupResourceState("container", "a" * 64, "present"),)),
        )
        self.records[record.evidence_record_id] = record
        return record

    def configure(self, request, snapshot):
        self.events.append("configure")
        return ApplyResult(True, snapshot), TrialConfigurationObservation(
            configurations=request.participant_configurations,
            evidence=(self.evidence(request, "configuration"),),
        )

    def observe(self, request, snapshot):
        if self.pending and not self.stopped:
            return TrialExecutionObservation(state="running", ceased=False, evidence=())
        return TrialExecutionObservation(
            state="failed" if self.failed else "succeeded",
            ceased=True,
            evidence=(self.evidence(request, "execution"),),
        )

    def capture(self, request, snapshot):
        self.events.append("capture")
        return ApplyResult(True, snapshot), TrialCaptureObservation(
            complete=True,
            evidence=(self.evidence(request, "capture"),),
        )

    def cleanup(self, request, outcome, snapshot):
        self.events.append("cleanup")
        return self.cleanups[request.execution_attempt_id].cleanup(
            request, outcome, snapshot
        )

    def verify(self, request, observation):
        if observation.kind == "cleanup":
            self.cleanups[request.execution_attempt_id].verify_observation(observation)
        else:
            assert all(
                self.records.get(record.evidence_record_id) == record
                for record in observation.evidence
            )

    def stop(self, request, cause, snapshot):
        self.stopped = True
        return ApplyResult(True, snapshot)
