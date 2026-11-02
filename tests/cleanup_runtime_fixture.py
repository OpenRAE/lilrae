"""Compose the real cleanup service into the released RAE trial lifecycle.

The other installed owners are test doubles. No reference-backend package or
LilRAE scheduling loop is used.
"""

import hashlib
import json
import yaml

from raes import admit_scenario_family, parse_sdl
from raes.canonical import canonical_sdl_digest

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
    realize_admitted_trial_entry,
)
from raes_runtime.registry import RuntimeTarget
from raes_runtime.runtime_trial_services import (
    TrialCaptureObservation,
    TrialConfigurationObservation,
    TrialExecutionObservation,
)

from aptl.backends.cleanup import DeclaredCleanup
from aptl.backends.raes_evaluator import AptlEvaluator
from aptl.backends.raes_orchestrator import AptlOrchestrator
from aptl.backends.raes_participant_runtime import AptlParticipantRuntime
from aptl.core.cleanup import CleanupBinding
from aptl.core.correlation.clock import FixedClockProvider
from aptl.core.runstore import LocalRunStore
from tests.structural_family_fixture import (
    FIXTURE,
    build_pack,
    _apparatus_context,
    _manifest_ref,
)
from tests.test_declared_cleanup import NativeOwner


def runtime_inputs(tmp_path):
    root = build_pack(tmp_path / "pack")
    (experiment,) = load_pack_experiments(root)
    context = _apparatus_context(experiment, FIXTURE)
    authority = context["execution_authority"].model_dump(mode="json")
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
    for node in family_payload["nodes"].values():
        node.update(os_distribution="ubuntu", os_version="22.04", architecture="x86_64")
        node.pop("runtime", None)
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
    compilation = compilation.with_experiment(
        type(compilation.experiment).model_validate(design)
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
    realized = realize_admitted_trial_entry(
        inputs=inputs, plan_entry_id=next(iter(inputs.plan.entries))
    )
    return inputs, realized.execution_plan.manifest


class Provisioner:
    def __init__(self, manifest):
        self.manifest = manifest

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
        return ApplyResult(
            True,
            snapshot.with_entries(
                entries,
                realization_observations=tuple(observations),
                realization_envelope=plan.realization_envelope,
            ),
            changed_addresses=[operation.address for operation in plan.operations],
        )


def target_for(manifest):
    return RuntimeTarget(
        name=manifest.name,
        manifest=manifest,
        provisioner=Provisioner(manifest),
        orchestrator=AptlOrchestrator(),
        evaluator=AptlEvaluator(),
        participant_runtime=AptlParticipantRuntime(deployment_backend=None),
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
