"""Native receipts reach the public runtime without backend ledger writes."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from raes import parse_sdl
from raes_backend_stubs.stubs import StubProvisioner
from raes_contracts.errors import ConflictError
from raes_contracts.run_scope import PlanScope
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_operations.run_artifacts import RunMaterializationArchive
from raes_runtime.manager import RuntimeManager
from raes_runtime.registry import RuntimeTarget

from aptl.backends.raes_manifest import create_aptl_manifest
from aptl.backends.raes_provisioner import AptlProvisioner
from aptl.core.config import AptlConfig
from aptl.core.deployment.lilrae_recorded_inventory import (
    RecordedChild,
    RecordedInventorySnapshot,
)
from aptl.core.scenario_bundle import project_tree_bundle
from tests.test_lilrae_docker_recording import _store
from tests.test_family_adapter_contract import family_input


class NativeFacts:
    def __init__(self, children):
        self.inventory = RecordedInventorySnapshot(tuple(children))
        self.reads = []

    def runtime_descendant_inventory(self, attempt_id):
        self.reads.append(attempt_id)
        return self.inventory


class ReportingProvisioner(AptlProvisioner):
    """Isolate external deployment; keep the production apply/report boundary."""

    def validate(self, plan):
        return []

    def realize_plan(self, plan):
        return SimpleNamespace(diagnostics=())

    def _apply_valid_plan(self, plan, snapshot, diagnostics, realization):
        return StubProvisioner(create_aptl_manifest().realization_envelope).apply(
            plan, snapshot
        )


def reporting_runtime(
    tmp_path,
    *,
    open_collection=True,
    manager_type=RuntimeManager,
    extra_sdl="",
    source_sdl=None,
    apparatus=(),
):
    from aptl.core.experiment.capture_plan import empty_capture_plan

    manifest = create_aptl_manifest(realization_preparation=bool(apparatus))
    store = _store(tmp_path, attempt="run-1")
    child = store.commit(
        store.begin("provision.node.holder", timeout_seconds=60), "b" * 64
    )
    native = NativeFacts([RecordedChild(child, platform="linux")])
    provisioner = ReportingProvisioner(
        tmp_path,
        AptlConfig(),
        native,
        project_tree_bundle(tmp_path, tmp_path / "demo.sdl.yaml"),
        capture_plan=replace(empty_capture_plan(), apparatus=apparatus),
        reporting_manifest=manifest,
    )
    provisioner.bind_attempt_id("run-1")
    from aptl.backends.raes_orchestrator import AptlOrchestrator
    from aptl.backends.raes_evaluator import AptlEvaluator
    from aptl.backends.raes_participant_runtime import AptlParticipantRuntime

    target = RuntimeTarget(
        name=manifest.name,
        manifest=manifest,
        provisioner=provisioner,
        orchestrator=AptlOrchestrator(reporting_manifest=manifest),
        evaluator=AptlEvaluator(reporting_manifest=manifest),
        participant_runtime=AptlParticipantRuntime(deployment_backend=native),
    )
    archive = RunMaterializationArchive(tmp_path / "archive")
    manager = manager_type(
        target, materialization_archive=archive, run_scope="run:run-1"
    )
    posture = "open" if open_collection else "closed"
    scenario = parse_sdl(
        source_sdl
        or f"""name: reporting
realization:
  default: closed
  scopes:
    - {{field_pointer: /nodes, posture: {posture}}}
    - {{field_pointer: /nodes/holder, posture: closed}}
nodes:
  holder: {{type: compute}}
{extra_sdl}"""
    )
    plan = manager.plan(scenario, run_scope=PlanScope(run_id="run-1"))
    assert plan.is_valid, plan.diagnostics
    return manager, provisioner, native, child, plan, archive


def test_public_manager_admits_recorded_child_and_derives_provenance(tmp_path):
    manager, provisioner, native, child, plan, archive = reporting_runtime(tmp_path)
    with manager:
        result = manager.apply(plan)
        assert result.success, result.diagnostics
        assert child.address in result.snapshot.entries
        assert child.address not in plan.provisioning.resources
        ledger = [
            r
            for r in result.snapshot.realization_provenance
            if r.address == child.address
        ]
        assert ledger
        assert all(r.provenance.value == "backend-realized" for r in ledger)
        assert all(r.explicitness.value == "open" for r in ledger)
        reports = [
            r for r in result.snapshot.materialization_attestations if r.inventory
        ]
        report = reports[-1].inventory
        assert report.descendants[0].source_address == "provision.node.holder"
        assert report.descendants[0].parent_address == "provision.node.holder"
        document = json.loads(
            json.dumps(__import__("yaml").safe_load(archive.read(reports[-1]).sdl))
        )
        assert (
            document["nodes"][child.address.removeprefix("provision.node.")]["os"]
            == "linux"
        )
        assert "b" * 64 not in repr(result.snapshot.materialization_attestations)
        assert native.reads == ["run-1"]


def test_native_source_image_evidence_does_not_invalidate_portable_inventory(tmp_path, monkeypatch):
    from aptl.backends._raes_observation_helpers import ObservedResource
    from aptl.backends.raes_diagnostics import snapshot_after_apply
    from raes_processor.semantics.realization import CONCERN_PAYLOAD_PATH

    manager, provisioner, _, _, plan, _ = reporting_runtime(tmp_path)
    image = {"digest": "sha256:" + "c" * 64}
    original = provisioner._apply_valid_plan

    def observed(request, previous, diagnostics, realization):
        result = original(request, previous, diagnostics, realization)
        facts = {
            address: ObservedResource(
                True, {CONCERN_PAYLOAD_PATH["node-type"]: "compute"},
                evidence={"source_image": image},
            ) for address in request.resources
        }
        return replace(result, snapshot=snapshot_after_apply(request, result.snapshot, facts),
                       details={"observation_evidence": {address: {"source_image": image} for address in facts}})

    monkeypatch.setattr(provisioner, "_apply_valid_plan", observed)
    with manager:
        result = manager.apply(plan)
        assert result.success, [(item.code, item.message) for item in result.diagnostics]
        assert result.snapshot.materialization_attestations
        assert provisioner.last_source_image_evidence == {
            address: image for address in plan.provisioning.resources
        }


def test_projected_native_readback_produces_resolvable_materialization_origins(tmp_path):
    from aptl.backends._runtime_concern_disclosure import _disclose
    from aptl.backends.lilrae_materialization_reporting import materialization_result
    from raes_processor.planner.materialization_inventory import admit_runtime_inventory

    fixture = Path(__file__).parent / "fixtures/packs/materialization-envelope/sdl/materialization-envelope.sdl.yaml"
    manager, _, _, _, execution, archive = reporting_runtime(tmp_path, source_sdl=fixture.read_text())
    with manager:
        request = replace(execution.provisioning, operation_id="native-readback", inventory_attempt_id="native-readback-attempt")
        result = StubProvisioner(execution.manifest.realization_envelope).apply(request, RuntimeSnapshot())
        address = "provision.node.smoke-box"
        entry = result.snapshot.entries[address]
        payload = deepcopy(entry.payload)
        network = payload["spec"]["node"]["runtime"]["network"]
        # Real daemon readback passes this safe projection before reporting.
        # The projector omits the authored non-state description.
        network["published_ports"] = _disclose("published-ports", network["published_ports"])
        assert "description" not in network["published_ports"][0]
        snapshot = result.snapshot.with_entries({**result.snapshot.entries, address: replace(entry, payload=payload)})
        reported = materialization_result(request, RuntimeSnapshot(), replace(result, snapshot=snapshot),
                                          execution.manifest, facts=RecordedInventorySnapshot())
        materialized = parse_sdl(reported.materialization_attestation.sdl)
        assert materialized.materialization_provenance.origins
        submission, admitted = admit_runtime_inventory(reported.materialization_attestation, request,
                                                       execution.manifest, RuntimeSnapshot(), snapshot, archive)
        assert address in admitted.entries
        record = archive.publish(submission.sdl)
        assert parse_sdl(archive.read(record).sdl).materialization_provenance.origins


def test_closed_collection_cannot_be_opened_by_reporting(tmp_path):
    manager, _, _, child, plan, _ = reporting_runtime(tmp_path, open_collection=False)
    with manager:
        result = manager.apply(plan)
        assert not result.success
        assert child.address not in result.snapshot.entries
        assert not result.snapshot.materialization_attestations


def test_refresh_retains_creation_identity_and_reports_removal(tmp_path, monkeypatch):
    from aptl.backends._raes_observation_helpers import ObservedResource

    monkeypatch.setattr(
        "aptl.backends.raes_observation.observe_realization",
        lambda *a, **kw: {
            "provision.node.holder": ObservedResource(True, {("node_kind",): "compute"})
        },
    )
    manager, _, native, child, plan, _ = reporting_runtime(tmp_path)
    with manager:
        initial = manager.apply(plan)
        assert initial.success, initial.diagnostics
        original = initial.snapshot.materialization_attestations[
            -1
        ].inventory.descendants[0]
        native.inventory = RecordedInventorySnapshot(
            (RecordedChild(child, "autoremoved", "linux"),)
        )
        refreshed = manager.refresh_inventory(plan)
        assert refreshed.success, refreshed.diagnostics
        assert child.address not in refreshed.snapshot.entries
        report = refreshed.snapshot.materialization_attestations[-1].inventory
        assert report.sequence == 2
        assert report.descendants[0].creation == original.creation
        assert report.descendants[0].state == "autoremoved"
        assert report.descendants[0].lifecycle is not None
        assert native.reads == ["run-1", "run-1"]


def test_incomplete_scan_retains_previously_accepted_children(tmp_path):
    manager, _, native, child, plan, _ = reporting_runtime(tmp_path)
    with manager:
        initial = manager.apply(plan)
        assert initial.success, initial.diagnostics
        native.inventory = RecordedInventorySnapshot(
            (), False, ("child-inspect-unavailable",)
        )
        refreshed = manager.refresh_inventory(plan)
        assert not refreshed.success
        assert refreshed.snapshot == initial.snapshot
        assert any(
            d.code == "runtime.inventory-coverage-invalid"
            for d in refreshed.diagnostics
        )


def test_forged_prior_attempt_is_rejected_without_losing_accepted_inventory(tmp_path):
    manager, _, native, child, plan, _ = reporting_runtime(tmp_path)
    with manager:
        initial = manager.apply(plan)
        assert initial.success, initial.diagnostics
        native.inventory = RecordedInventorySnapshot(
            (RecordedChild(replace(child, attempt_id="other")),)
        )
        refreshed = manager.refresh_inventory(plan)
        assert not refreshed.success
        assert refreshed.snapshot == initial.snapshot


def test_local_archive_uses_custom_store_and_refuses_sealed_run(tmp_path):
    from aptl.backends.lilrae_materialization_archive import (
        LilraeMaterializationArchive,
    )
    from aptl.core.runstore import LocalRunStore
    from aptl.core.runstore import SEAL_MARKER_RELPATH

    manager, _, _, _, plan, source_archive = reporting_runtime(tmp_path)
    with manager:
        result = manager.apply(plan)
        assert result.success, result.diagnostics
    record = result.snapshot.materialization_attestations[-1]
    store = LocalRunStore(tmp_path / "custom-store")
    archive = LilraeMaterializationArchive(store, "run-1")
    copied = archive.publish(source_archive.read(record).sdl)
    artifact = (
        store.get_run_path("run-1") / "materialization" / copied.reference.ref_path
    )
    assert artifact.is_file()
    assert artifact.stat().st_mode & 0o777 == 0o600
    assert archive.read(copied) == source_archive.read(record)
    before = set(artifact.parent.iterdir())
    store.commit_seal_marker("run-1", {"sealed": True})
    sealed_sdl = source_archive.read(record).sdl
    with pytest.raises(ValueError, match="sealed"):
        archive.publish(sealed_sdl)
    assert set(artifact.parent.iterdir()) == before


def test_archive_publication_cannot_follow_a_replaced_run_parent(tmp_path, monkeypatch):
    import os
    from aptl.backends.lilrae_materialization_archive import (
        LilraeMaterializationArchive,
    )
    from aptl.core.runstore import LocalRunStore
    from aptl.utils.pathsafe import PathContainmentError

    manager, _, _, _, plan, source = reporting_runtime(tmp_path)
    with manager:
        result = manager.apply(plan)
        assert result.success
    content = source.read(result.snapshot.materialization_attestations[-1]).sdl
    store = LocalRunStore(tmp_path / "private-runs")
    archive = LilraeMaterializationArchive(store, "run-1")
    run = store.get_run_path("run-1")
    foreign = tmp_path / "foreign"
    (foreign / "materialization").mkdir(parents=True)
    close = os.close
    attacked = False

    def replace_parent(descriptor):
        nonlocal attacked
        if not attacked and os.readlink(f"/proc/self/fd/{descriptor}") == str(
            run / "materialization"
        ):
            attacked = True
            run.rename(run.with_name("retained-run"))
            run.symlink_to(foreign, target_is_directory=True)
        close(descriptor)

    monkeypatch.setattr(os, "close", replace_parent)
    try:
        archive.publish(content)
    except PathContainmentError, ValueError, OSError:
        pass
    assert attacked
    assert not tuple(foreign.rglob("*.sdl"))


def test_product_manager_accepts_protected_archive_owner(tmp_path):
    from aptl.backends.raes_planning_compat import AptlRuntimeManager

    manager, _, _, child, plan, _ = reporting_runtime(
        tmp_path, manager_type=AptlRuntimeManager
    )
    with manager:
        result = manager.apply(plan)
        assert result.success, result.diagnostics
        assert child.address in result.snapshot.entries


def test_evaluation_and_workflow_phases_describe_accepted_descendants(tmp_path):
    extra = """
entities:
  blue: {role: blue}
propositions:
  health:
    description: Observed node health.
    subjects: [nodes.holder]
    basis: declared_state
    predicate:
      kind: boolean
      property: health
      semantic_ref: urn:aces:observable:health
      operator: equals
      expected: true
    quantifier: all
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
objectives:
  validate:
    owner: blue
    success: {assertions: [health]}
workflows:
  execution:
    start: run
    steps:
      run: {type: objective, objective: validate, on_success: finish}
      finish: {type: end}
"""
    manager, _, _, child, plan, _ = reporting_runtime(tmp_path, extra_sdl=extra)
    with manager:
        result = manager.apply(plan)
        assert result.success, result.diagnostics
        assert child.address in result.snapshot.entries
        assert result.snapshot.evaluation_results
        assert result.snapshot.orchestration_results
        assert len(result.snapshot.materialization_attestations) == 3


def test_start_handoff_archives_and_returns_refreshed_inventory(tmp_path):
    from aptl.backends.raes import _apply_execution_plan
    from aptl.core.runstore import LocalRunStore

    manager, _, native, child, plan, _ = reporting_runtime(tmp_path)
    target = manager._target
    manager.close()
    store = LocalRunStore(tmp_path / "custom-runs")
    failure, snapshot, applied_manager = _apply_execution_plan(
        target, plan, run_store=store, run_id="run-1"
    )
    with applied_manager:
        assert failure is None, failure
        assert child.address in snapshot.entries
        assert snapshot.materialization_attestations[-1].inventory.sequence == 2
        assert native.reads == ["run-1", "run-1"]
        assert list((store.get_run_path("run-1") / "materialization").rglob("*.sdl"))


def test_plan_options_bind_run_identity_before_sealing(tmp_path):
    from aptl.backends.raes_planning_compat import (
        AptlPlanningOptions,
        plan_aptl_scenario,
    )

    manager, provisioner, _, _, _, _ = reporting_runtime(tmp_path)
    with manager:
        plan = plan_aptl_scenario(
            target=manager._target,
            scenario=parse_sdl("name: bound\nnodes: {holder: {type: compute}}"),
            options=AptlPlanningOptions(run_scope=PlanScope(run_id="chosen-run")),
        )
        assert plan.is_valid, plan.diagnostics
        assert plan.provisioning.materialization_source.run_id == "chosen-run"


def test_lab_resolves_one_run_identity_before_admission(tmp_path):
    from aptl.core.lab import _LabStartContext, _resolve_run_target

    ctx = _LabStartContext(project_dir=tmp_path, config=AptlConfig(), skip_seed=True)
    first = _resolve_run_target(ctx)
    assert ctx.run_id == first[1]
    assert ctx.run_store is first[0]
    assert _resolve_run_target(ctx) == first


def test_later_evaluation_retains_the_protected_archive(tmp_path):
    from aptl.backends.raes_planning_compat import AptlRuntimeManager
    from raes_contracts.runtime_state import OperationState

    manager, _, _, child, plan, _ = reporting_runtime(
        tmp_path, manager_type=AptlRuntimeManager
    )
    with manager:
        initial = manager.apply(plan)
        assert initial.success, initial.diagnostics
        count = len(initial.snapshot.materialization_attestations)
        receipt = manager.evaluate(plan, idempotency_key="later-evaluation")
        assert receipt.accepted, receipt.diagnostics
        operation = manager.get_operation(receipt.operation_id)
        assert operation.state is OperationState.SUCCEEDED, operation.diagnostics
        assert child.address in manager.snapshot.entries
        assert len(manager.snapshot.materialization_attestations) == count + 1


def test_configured_target_reports_its_exact_manifest(tmp_path, monkeypatch):
    from aptl.backends.raes import create_aptl_runtime_target
    from aptl.backends._raes_runtime_target_options import RuntimeTargetOptions
    from aptl.core.experiment.capture_registry import CollectorRegistry
    from aptl_techvault.capture_registrations import BUILTIN_REGISTRATIONS

    native = NativeFacts([])
    selection = SimpleNamespace(
        registry=CollectorRegistry(BUILTIN_REGISTRATIONS),
        contribution=SimpleNamespace(proposition_interpreter=None),
    )
    target = create_aptl_runtime_target(
        project_dir=tmp_path,
        config=AptlConfig(),
        backend=native,
        bundle=project_tree_bundle(tmp_path, tmp_path / "scenario.sdl.yaml"),
        options=RuntimeTargetOptions(capture_selection=selection),
    )
    monkeypatch.setattr(
        target.provisioner,
        "realize_plan",
        lambda request: SimpleNamespace(diagnostics=()),
    )
    monkeypatch.setattr(
        target.provisioner,
        "_apply_valid_plan",
        lambda request, previous, *args: StubProvisioner(
            target.manifest.realization_envelope
        ).apply(request, previous),
    )
    target.provisioner.bind_attempt_id("run-1")
    with RuntimeManager(
        target,
        materialization_archive=RunMaterializationArchive(tmp_path / "archive"),
        run_scope="run:run-1",
    ) as manager:
        plan = manager.plan(
            parse_sdl("name: configured\nnodes: {holder: {type: compute}}"),
            run_scope=PlanScope(run_id="run-1"),
        )
        assert plan.is_valid, plan.diagnostics
        result = manager.apply(plan)
        assert result.success, result.diagnostics
        assert result.snapshot.materialization_attestations


def test_one_snapshot_preserves_all_three_value_origins(tmp_path, monkeypatch):
    from aptl.backends._raes_operational_observation import (
        operational_realization_observations,
    )
    from aptl.backends._raes_observation_helpers import ObservedResource
    from raes_contracts.realization_observation import ObservedOperatingSystemIdentity

    source = """name: concern-origins
variables:
  system: {type: string, description: Native platform, default: linux}
realization:
  default: closed
  scopes:
    - {field_pointer: /nodes, posture: open}
    - {field_pointer: /nodes/holder, posture: closed}
nodes:
  holder: {type: compute, os: '${system}'}
"""
    manager, provisioner, _, child, plan, _ = reporting_runtime(
        tmp_path, source_sdl=source
    )
    apply_world = provisioner._apply_valid_plan

    def observed_world(*args):
        result = apply_world(*args)
        observations = operational_realization_observations(
            plan=args[0],
            observations={
                "provision.node.holder": ObservedResource(
                    True,
                    operating_system=ObservedOperatingSystemIdentity(
                        family="linux", distribution="debian", version="12"
                    ),
                )
            },
            envelope=create_aptl_manifest().realization_envelope,
        )
        return replace(
            result,
            operational_realization_observations=(
                *result.operational_realization_observations,
                *observations,
            ),
        )

    monkeypatch.setattr(provisioner, "_apply_valid_plan", observed_world)
    with manager:
        result = manager.apply(plan)
        assert result.success, result.diagnostics
        ledger = {
            (r.address, r.requirement_kind): r
            for r in result.snapshot.realization_provenance
        }
        authored = ledger["provision.node.holder", "node-type"]
        derived = ledger["provision.node.holder", "os-family"]
        realized = ledger[child.address, "node-type"]
        assert (authored.explicitness.value, authored.provenance.value) == (
            "exact",
            "author-declared",
        )
        assert (derived.explicitness.value, derived.provenance.value) == (
            "constrained",
            "processor-derived",
        )
        assert (realized.explicitness.value, realized.provenance.value) == (
            "open",
            "backend-realized",
        )


def test_runtime_refuses_a_plan_from_another_run(tmp_path):
    manager, _, native, _, plan, _ = reporting_runtime(tmp_path)
    with manager:
        foreign = replace(
            plan, provisioning=replace(plan.provisioning, run_id="foreign")
        )
        with pytest.raises(ConflictError, match="run scope"):
            manager.apply(foreign)
        assert not native.reads
        assert not manager.snapshot.materialization_attestations


def test_planning_keeps_the_sealed_family_run_identity(tmp_path, family_input):
    from tests.test_family_adapter_contract import BACKEND
    from aptl.backends.scenario_family import admit_family_trial, FamilyTrialInput
    from aptl.backends.raes_planning_compat import (
        plan_aptl_scenario,
        AptlPlanningOptions,
    )

    bundle, family, trial_plan = family_input()
    trial = admit_family_trial(
        bundle, BACKEND, FamilyTrialInput(trial_plan, "entry-a", family)
    )
    bundle = replace(bundle, trial=trial)
    manager, provisioner, native, _, _, _ = reporting_runtime(tmp_path)
    provisioner.bundle = bundle
    with manager:
        plan = plan_aptl_scenario(
            target=manager._target,
            scenario=trial.scenario,
            options=AptlPlanningOptions(),
        )
        assert plan.is_valid, plan.diagnostics
        assert (
            plan.provisioning.materialization_source.run_id == trial.provenance.run_id
        )
        other_run = AptlPlanningOptions(run_scope=PlanScope(run_id="other"))
        with pytest.raises(ValueError, match="family-run-identity-mismatch"):
            plan_aptl_scenario(
                target=manager._target,
                scenario=trial.scenario,
                options=other_run,
            )
        assert not native.reads


def test_legacy_target_keeps_its_default_control_plane_scope():
    from aptl.backends.raes_planning_compat import AptlRuntimeManager
    from raes_backend_stubs.stubs import create_stub_target
    from raes_contracts.runtime_state import OperationState

    with AptlRuntimeManager(create_stub_target()) as manager:
        plan = manager.plan(parse_sdl("name: legacy\nnodes: {holder: {type: compute}}"))
        assert plan.is_valid, plan.diagnostics
        initial = manager.apply(plan)
        assert initial.success, initial.diagnostics
        receipt = manager.evaluate(plan, idempotency_key="legacy-evaluation")
        assert receipt.accepted, receipt.diagnostics
        assert (
            manager.get_operation(receipt.operation_id).state
            is OperationState.SUCCEEDED
        )


def test_public_apply_binds_the_run_before_deployment(tmp_path, monkeypatch):
    manager, provisioner, native, _, plan, _ = reporting_runtime(tmp_path)
    provisioner.bind_attempt_id(None)
    apply_world = provisioner._apply_valid_plan

    def admitted_world(*args):
        assert provisioner._attempt_id == "run-1"
        return apply_world(*args)

    monkeypatch.setattr(provisioner, "_apply_valid_plan", admitted_world)
    with manager:
        result = manager.apply(plan)
        assert result.success, result.diagnostics
        assert native.reads == ["run-1"]


def test_conflicting_run_binding_prevents_deployment(tmp_path, monkeypatch):
    manager, provisioner, native, _, plan, _ = reporting_runtime(tmp_path)
    provisioner.bind_attempt_id("different-run")
    monkeypatch.setattr(
        provisioner,
        "_apply_valid_plan",
        lambda *args: pytest.fail("conflicting run must not deploy"),
    )
    with manager:
        result = manager.apply(plan)
        assert not result.success
        assert not native.reads
        assert any(
            d.code == "lilrae.provisioner.run-identity-mismatch"
            for d in provisioner.last_failure_diagnostics
        )
        assert "different-run" not in repr(result.diagnostics)
