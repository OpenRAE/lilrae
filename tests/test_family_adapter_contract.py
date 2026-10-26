"""Public family qualification and detached trial handoff contracts (#1414)."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from aptl.backends.identity import BackendIdentity
from aptl.backends.scenario_family import (
    FAMILY_API_VERSION,
    QualifiedFamilyTarget,
    family_provider_matches,
)
from aptl.core.scenario_bundle import PackIdentity


@pytest.fixture
def family_input(tmp_path):
    import json
    from pathlib import Path
    from raes import parse_sdl_file, canonical_sdl_digest
    from raes_contracts.corpus import FIXTURES, corpus_family_root
    from pydantic import TypeAdapter
    from raes_contracts.contracts import (
        AdmittedTrialEntryModel,
        AdmittedTrialPlanModel,
        seal_admitted_trial_entry,
        seal_admitted_trial_plan,
    )
    from aptl.core.scenario_bundle import ScenarioBundle, ScenarioSourceKind

    (tmp_path / "module.yaml").write_text(
        "name: module\nversion: 1.0.0\nmodule:\n  id: fixture/nodes\n  version: 1.0.0\n  exports: {nodes: [primary]}\nnodes:\n  primary: {type: compute, resources: {ram: 1 GiB, cpu: 1}}\n"
    )
    sdl = tmp_path / "family.yaml"
    sdl.write_text(
        "name: family-a\nimports:\n  - {path: module.yaml, namespace: shared, version: 1.0.0}\nvariables:\n  payload_path: {type: string, default: /opt/a, allowed_values: [/opt/a, /opt/b]}\ncontent:\n  payload: {type: file, target: shared.primary, path: '${payload_path}'}\nvariation_points:\n  point-a:\n    kind: parameter\n    target: {kind: variable, variable: payload_path}\n    domain: {kind: enum, values: [/opt/a, /opt/b]}\n"
    )
    family = parse_sdl_file(sdl)
    bundle = ScenarioBundle(
        "example-family", tmp_path, sdl, ScenarioSourceKind.ENV_PACK, PACK
    )

    def build(value="/opt/a", *, capture=False):
        selected_family = family
        if capture:
            if "evidence_requirements:" not in sdl.read_text():
                sdl.write_text(
                    sdl.read_text()
                    + """evidence_requirements:
  payload-readiness:
    description: Records the selected payload readiness.
    source_refs: [nodes.shared.primary]
    scope_refs: [nodes.shared.primary]
    scope: Selected payload readiness.
    boundary_kind: system_under_test
    channel: api_response
    media_types: [application/json]
    artifact_role: service_materialization_readback
    sensitivity: plain
    redaction: redact_secrets
    integrity: checksum
    retention: run_lifetime
    loss_disclosure: required
"""
                )
            selected_family = parse_sdl_file(sdl)
        fixture = (
            Path(corpus_family_root(FIXTURES))
            / "plans/admitted-trial-plan-v1/valid/minimal.json"
        )
        payload = json.loads(fixture.read_text())
        entry = payload["entries"]["entry-a"]
        entry.pop("entry_digest")
        entry["bindings"] = []
        entry["stochastic_draws"] = []
        entry["selections"][0]["outcome"] = {"kind": "literal", "value": value}
        entry = {
            name: TypeAdapter(
                AdmittedTrialEntryModel.model_fields[name].annotation
            ).validate_python(value)
            for name, value in entry.items()
        }
        payload["entries"]["entry-a"] = seal_admitted_trial_entry(**entry)
        payload["input_refs"]["scenario_family_ref"]["ref_digest"] = (
            canonical_sdl_digest(selected_family).value
        )
        payload["stochastic_controls"] = {}
        payload.pop("plan_digest")
        payload = {
            name: TypeAdapter(
                AdmittedTrialPlanModel.model_fields[name].annotation
            ).validate_python(value)
            for name, value in payload.items()
        }
        plan = seal_admitted_trial_plan(**payload)
        return bundle, selected_family, plan

    return build


PACK = PackIdentity("example-family", "1.0.0", "sha256:" + "a" * 64)
BACKEND = BackendIdentity(
    "aptl", "0.1.0", "full-remote-control-plane", provider="docker", transport="docker"
)
TARGET = QualifiedFamilyTarget(PACK, "family-a", "sha256:" + "b" * 64, BACKEND)


def _provider(*targets):
    return SimpleNamespace(family_api_version="1", qualified_family_targets=targets)


def test_family_qualification_is_atomic():
    other = replace(
        TARGET,
        pack=replace(PACK, pack_version="2.0.0", set_digest="sha256:" + "c" * 64),
    )
    provider = _provider(TARGET, other)
    assert family_provider_matches(provider, TARGET)
    assert family_provider_matches(provider, other)
    cross_pair = replace(TARGET, pack=replace(PACK, set_digest=other.pack.set_digest))
    assert not family_provider_matches(provider, cross_pair)


def test_serving_context_exposes_no_trial_or_scenario():
    from aptl.backends.pack_interaction import PackBackendInteractionContext

    context = PackBackendInteractionContext(PACK, BACKEND, ("nodes.primary",))
    assert not hasattr(context, "trial")
    assert not hasattr(context, "scenario")


def test_baseline_write_path_rejection_returns_false(monkeypatch, tmp_path):
    from aptl_techvault.evidence import techvault_enrollment_baseline as baseline
    from aptl.utils.pathsafe import PathContainmentError, REASON_SYMLINK

    def reject(*args, **kwargs):
        raise PathContainmentError(REASON_SYMLINK, "private-path-canary")

    monkeypatch.setattr(baseline, "replace_private_nofollow", reject)
    assert baseline.record_enrollment_baseline(tmp_path, {"agent": "001"}) is False


def test_family_retry_operations_keep_admitted_aliases_and_hide_environment():
    from aptl.backends.scenario_runtime_hooks import AdmittedRuntimeOperations
    from aptl.core.lab_types import LabResult

    restarted = []
    backend = SimpleNamespace(
        container_inspect=lambda name: {
            "State": {"Status": "running", "Running": True},
            "RestartCount": 1,
            "Config": {"Env": ["TOKEN=credential-canary"]},
        },
        container_restart=lambda name: (
            restarted.append(name) or LabResult(success=True)
        ),
    )
    node = SimpleNamespace(
        name="manager", container_name="runtime-manager", aliases=("manager-alias",)
    )
    operations = AdmittedRuntimeOperations(backend, (node,))
    info = operations.container_inspect("manager-alias")
    assert info["State"]["Status"] == "running"
    assert "credential-canary" not in str(info)
    assert operations.container_restart("manager").success
    assert restarted == ["manager"]
    with pytest.raises(ValueError, match="^runtime-node-not-admitted$"):
        operations.container_restart("outside")


def test_family_native_capture_uses_trial_entry_identity(
    monkeypatch, family_input, tmp_path
):
    from aptl.backends.scenario_family import FamilyTrialInput, admit_family_trial
    from aptl.backends.raes_evidence_acquisition import (
        NativeEvidenceRequest,
        acquire_native_evidence,
    )
    from aptl.core.experiment.capture_plan import empty_capture_plan
    from aptl.core.runstore import LocalRunStore

    bundle, family, plan = family_input()
    trial = admit_family_trial(
        bundle, BACKEND, FamilyTrialInput(plan, "entry-a", family)
    )
    selected = SimpleNamespace(
        context=SimpleNamespace(trial=trial),
        contribution=SimpleNamespace(
            native_registration_ids=frozenset(), runtime_adapter=None
        ),
    )
    request = NativeEvidenceRequest(
        empty_capture_plan(),
        object(),
        SimpleNamespace(nodes=()),
        tmp_path,
        {},
        LocalRunStore(tmp_path / "archive"),
        trial.provenance.run_id,
        selected,
    )
    monkeypatch.setattr(
        "aptl.backends.scenario_capture.family_capture_sources", lambda request: {}
    )
    monkeypatch.setattr(
        "aptl.backends._raes_native_evidence_acquisition.acquire_evidence",
        lambda **kw: kw["scope"],
    )
    scope = acquire_native_evidence(request)
    assert scope.planned_trial_id == trial.provenance.plan_entry_id
    assert scope.planned_trial_id != request.plan.plan_id
    with pytest.raises(ValueError, match="^family-run-identity-mismatch$"):
        acquire_native_evidence(replace(request, run_id="wrong-run"))
    assert not request.run_store.get_run_path("wrong-run").exists()


def test_resumed_capture_keeps_sealed_trial_scope(family_input):
    from aptl.backends.scenario_family import FamilyTrialInput, admit_family_trial
    from aptl.backends.scenario_capture import (
        ScenarioCaptureResumeContext,
        capture_run_scope,
    )

    bundle, family, plan = family_input()
    trial = admit_family_trial(
        bundle, BACKEND, FamilyTrialInput(plan, "entry-a", family)
    )
    context = ScenarioCaptureResumeContext(trial.target, trial.identity())
    scope = capture_run_scope(
        context, trial.provenance.run_id, "capture-plan-other", "stop"
    )
    assert scope.planned_trial_id == "entry-a"
    assert scope.attempt_id == "stop"
    with pytest.raises(ValueError, match="^family-run-identity-mismatch$"):
        capture_run_scope(context, "wrong-run", "capture-plan-other", "stop")


@pytest.mark.parametrize(
    "field,value",
    [
        ("family_api_version", "0"),
        ("family_api_version", "2"),
        ("qualified_family_targets", ()),
        ("qualified_family_targets", (TARGET, TARGET)),
        ("qualified_family_targets", (object(),)),
    ],
)
def test_bad_family_metadata_is_bounded(field, value):
    provider = _provider(TARGET)
    setattr(provider, field, value)
    with pytest.raises(ValueError, match="^family-provider-metadata-invalid$"):
        family_provider_matches(provider, TARGET)


def test_wrong_backend_never_inherits_family_qualification():
    assert not family_provider_matches(
        _provider(TARGET), replace(TARGET, backend=replace(BACKEND, transport="ssh"))
    )
    assert FAMILY_API_VERSION == "1"


def test_provider_metadata_exception_does_not_escape():
    class Broken:
        @property
        def family_api_version(self):
            raise RuntimeError("credential-canary")

    with pytest.raises(ValueError, match="^family-provider-metadata-invalid$") as error:
        family_provider_matches(Broken(), TARGET)
    assert "credential-canary" not in str(error.value)


def test_two_trials_keep_one_family_and_detached_snapshot(family_input):
    from aptl.backends.scenario_family import FamilyTrialInput, admit_family_trial

    trials = []
    for value in ("/opt/a", "/opt/b"):
        bundle, family, plan = family_input(value)
        trial = admit_family_trial(
            bundle, BACKEND, FamilyTrialInput(plan, "entry-a", family)
        )
        assert trial.scenario.content["payload"].path == value
        assert trial.provenance.plan_digest == plan.plan_digest
        assert trial.provenance.plan_entry_id == "entry-a"
        assert value not in repr(trial)
        trial.scenario.content.clear()
        assert "payload" in trial.scenario.content
        trials.append(trial)
    assert trials[0].target == trials[1].target
    assert trials[0].snapshot_digest != trials[1].snapshot_digest


def test_trial_rejects_substituted_source_and_broken_seal(family_input):
    from aptl.backends.scenario_family import FamilyTrialInput, admit_family_trial

    bundle, family, plan = family_input()
    altered = plan.model_copy(deep=True)
    altered.entries["entry-a"].selections[0].outcome.__dict__["value"] = "/opt/b"
    with pytest.raises(ValueError, match="^family-trial-invalid$"):
        admit_family_trial(
            bundle, BACKEND, FamilyTrialInput(altered, "entry-a", family)
        )
    bundle.sdl_path.write_text(bundle.sdl_path.read_text().replace("/opt/b", "/opt/c"))
    with pytest.raises(ValueError, match="^family-trial-invalid$"):
        admit_family_trial(bundle, BACKEND, FamilyTrialInput(plan, "entry-a", family))


def test_family_discovery_requires_all_seams_from_one_distribution(
    monkeypatch, family_input
):
    from aptl.backends import scenario_family as contract

    bundle, family, plan = family_input()
    trial = contract.admit_family_trial(
        bundle, BACKEND, contract.FamilyTrialInput(plan, "entry-a", family)
    )
    entries = []
    for group, selector, version, method in contract.family_capabilities(trial.target):
        provider = _provider(trial.target)
        provider.extension_api_version = version
        provider.provider_id = provider.plugin_id = "example-provider"
        setattr(provider, method, lambda context: None)
        entries.append(
            SimpleNamespace(
                group=group,
                name=selector,
                load=lambda p=provider: p,
                dist=SimpleNamespace(name="example-adapter", version="1.0"),
            )
        )
    monkeypatch.setattr(
        contract.metadata,
        "entry_points",
        lambda **kw: [e for e in entries if e.group == kw["group"]],
    )
    selections = contract.require_family_capabilities(trial)
    assert len(selections) == 6
    assert {selection.distribution for selection in selections} == {"example-adapter"}
    entries.pop()
    with pytest.raises(ValueError, match="^family-provider-missing$"):
        contract.require_family_capabilities(trial)


def test_family_discovery_rejects_duplicates_and_load_failures(monkeypatch):
    from aptl.backends import scenario_family as contract

    provider = _provider(TARGET)
    provider.extension_api_version = "1"
    provider.provider_id = "example-provider"
    provider.resolve = lambda context: None
    entry = SimpleNamespace(
        name="example-family.aptl",
        load=lambda: provider,
        dist=SimpleNamespace(name="example-adapter", version="1.0"),
    )
    monkeypatch.setattr(contract.metadata, "entry_points", lambda **kw: [entry, entry])
    with pytest.raises(ValueError, match="^family-provider-ambiguous$"):
        contract.select_family_provider(
            "aptl.scenario_capture", entry.name, "1", "resolve", TARGET
        )

    def broken():
        raise RuntimeError("credential-canary")

    entry.load = broken
    monkeypatch.setattr(contract.metadata, "entry_points", lambda **kw: [entry])
    with pytest.raises(ValueError, match="^family-provider-load-failed$"):
        contract.select_family_provider(
            "aptl.scenario_capture", entry.name, "1", "resolve", TARGET
        )


def test_preparation_consumes_exact_trial_without_rebinding(monkeypatch, family_input):
    from aptl.backends import scenario_family as contract
    from aptl.backends._raes_admission_helpers import prepare_admission_scenario

    bundle, family, plan = family_input("/opt/b")
    trial = contract.admit_family_trial(
        bundle, BACKEND, contract.FamilyTrialInput(plan, "entry-a", family)
    )
    bundle = replace(bundle, trial=trial)
    monkeypatch.setattr(
        "aptl.backends.scenario_runtime_parameters.resolve_runtime_parameters",
        lambda b: pytest.fail("must not regenerate sealed parameters"),
    )
    scenario, parameters, _ = prepare_admission_scenario(bundle, None, None)
    assert parameters is None
    assert scenario.content["payload"].path == "/opt/b"
    assert scenario.instantiation_provenance.trial.plan_digest == plan.plan_digest
    with pytest.raises(ValueError, match="^family-trial-parameter-collision$"):
        prepare_admission_scenario(bundle, {"payload_path": "/opt/a"}, None)


def test_existing_serving_and_capture_seams_deliver_family_trial(
    monkeypatch, family_input
):
    from aptl.backends import scenario_family as family_contract
    from aptl.backends.pack_interaction import (
        PackBackendInteractionContext,
        PackBackendInteractionResult,
        ComponentGroupMembership,
    )
    from aptl.backends.pack_interaction_discovery import (
        resolve_pack_backend_interaction,
    )
    from aptl.backends.scenario_capture import (
        ScenarioCaptureContext,
        ScenarioCaptureContribution,
    )
    from aptl.backends.scenario_capture_discovery import resolve_scenario_capture

    bundle, family, plan = family_input()
    trial = family_contract.admit_family_trial(
        bundle, BACKEND, family_contract.FamilyTrialInput(plan, "entry-a", family)
    )
    provider = _provider(trial.target)
    provider.provider_id = "example-family-provider"
    provider.extension_api_version = "1"
    seen = []

    def resolve(context):
        if isinstance(context, PackBackendInteractionContext):
            assert not hasattr(context, "trial")
            seen.append(context.component_addresses)
            return PackBackendInteractionResult(
                tuple(
                    ComponentGroupMembership(a, ("lab",))
                    for a in context.component_addresses
                )
            )
        seen.append(context.trial.snapshot_digest)
        context.trial.scenario.content.clear()
        return ScenarioCaptureContribution(())

    provider.resolve = resolve
    entry = SimpleNamespace(
        name="example-family.aptl",
        load=lambda: provider,
        dist=SimpleNamespace(name="example-adapter", version="1.0"),
    )
    monkeypatch.setattr(family_contract.metadata, "entry_points", lambda **kw: [entry])
    serving = resolve_pack_backend_interaction(
        PackBackendInteractionContext(PACK, BACKEND, ("nodes.primary",)), trial=trial
    )
    capture = resolve_scenario_capture(
        ScenarioCaptureContext(PACK, BACKEND, trial=trial)
    )
    assert serving.groups_for("nodes.primary") == ("lab",)
    assert capture.distribution == "example-adapter"
    assert seen == [("nodes.primary",), trial.snapshot_digest]
    assert "payload" in trial.scenario.content


def test_family_admission_rejects_missing_capability_before_backend(
    monkeypatch, family_input
):
    from aptl.backends import scenario_family as contract
    from aptl.backends.raes import admit_raes_scenario
    from aptl.core.config import AptlConfig

    bundle, family, plan = family_input()
    monkeypatch.setattr(contract.metadata, "entry_points", lambda **kw: [])
    monkeypatch.setattr(
        "aptl.backends.raes.prepare_runtime_orchestration_for_scenario",
        lambda *a: pytest.fail("backend authority must not be prepared"),
    )
    with pytest.raises(ValueError, match="^family-provider-missing$"):
        admit_raes_scenario(
            bundle.root,
            AptlConfig(),
            object(),
            bundle=bundle,
            trial=contract.FamilyTrialInput(plan, "entry-a", family),
        )


def test_startup_planning_and_verifier_receive_same_trial(monkeypatch, family_input):
    from aptl.backends import scenario_family as contract
    from aptl.backends.scenario_startup import (
        select_scenario_startup,
        ScenarioStartupPlan,
    )
    from aptl.backends.scenario_planning_compatibility import (
        ScenarioPlanningCompatibilityContext,
        PlanningCompatibilityDecision,
    )
    from aptl.backends.scenario_planning_compatibility_discovery import (
        resolve_scenario_planning_compatibility,
    )
    from aptl.validation.scenario_verification import (
        VerificationContext,
        ScenarioIdentity,
        VerificationReport,
        VerificationStatus,
        VerificationCheck,
    )
    from aptl.validation.scenario_verification_discovery import verify_scenario

    bundle, family, plan = family_input()
    trial = contract.admit_family_trial(
        bundle, BACKEND, contract.FamilyTrialInput(plan, "entry-a", family)
    )
    bundle = replace(bundle, trial=trial)
    seen = []

    def entries(**kw):
        provider = _provider(trial.target)
        provider.provider_id = provider.plugin_id = "example-provider"
        group, selector, version, method = next(
            c for c in contract.family_capabilities(trial.target) if c[0] == kw["group"]
        )
        provider.extension_api_version = version

        def resolve(context):
            seen.append(context.trial.snapshot_digest)
            if group == "aptl.scenario_startup":
                return ScenarioStartupPlan("scripts/seed.sh", ("lab",), ("lab",))
            return PlanningCompatibilityDecision()

        def run(context):
            seen.append(context.trial.snapshot_digest)
            return VerificationReport(
                VerificationStatus.PASSED,
                context.scenario,
                context.backend,
                run_id=context.run_id,
                attempt_id=context.attempt_id,
                checks=(
                    VerificationCheck("family-readback", VerificationStatus.PASSED),
                ),
            )

        provider.resolve, provider.run = resolve, run
        return [
            SimpleNamespace(
                name=selector,
                load=lambda: provider,
                dist=SimpleNamespace(name="example-adapter", version="1.0"),
            )
        ]

    monkeypatch.setattr(contract.metadata, "entry_points", entries)
    assert select_scenario_startup(bundle).plan.seed_script == "scripts/seed.sh"
    assert (
        resolve_scenario_planning_compatibility(
            ScenarioPlanningCompatibilityContext(PACK, BACKEND, trial)
        ).provider_id
        == "example-provider"
    )
    scenario = ScenarioIdentity(
        "family-a", trial.target.family_digest, "env-pack", "1.0.0"
    )
    report = verify_scenario(
        VerificationContext("run-a", "attempt-a", scenario, BACKEND, trial=trial)
    )
    assert report.status is VerificationStatus.PASSED
    assert seen == [trial.snapshot_digest] * 3


def test_bundled_adapter_uses_no_private_core_imports():
    import ast
    from pathlib import Path

    violations = []
    for path in [
        *Path("src/aptl_techvault").rglob("*.py"),
        *Path("tests/fixtures/family_adapter/family_adapter").rglob("*.py"),
    ]:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "aptl."
            ):
                if any(part.startswith("_") for part in node.module.split(".")) or any(
                    alias.name.startswith("_") for alias in node.names
                ):
                    violations.append(f"{path.name}:{node.lineno}")
    assert not violations, violations


def test_capture_source_context_hides_store_and_ungranted_credentials():
    from aptl.backends.scenario_capture import capture_source_context

    request = SimpleNamespace(
        backend=object(),
        realization=SimpleNamespace(nodes=()),
        environment={"ALLOWED_KEY": "permitted", "OTHER_KEY": "credential-canary"},
        capture_selection=SimpleNamespace(
            contribution=SimpleNamespace(runtime_environment_keys=("ALLOWED_KEY",)),
            context=SimpleNamespace(trial=None),
        ),
        run_store=object(),
        project_dir="/private/operator/project",
        run_id="run-a",
    )
    context = capture_source_context(request)
    assert dict(context.environment) == {"ALLOWED_KEY": "permitted"}
    assert not hasattr(context, "run_store")
    assert not hasattr(context, "project_dir")
    assert "credential-canary" not in repr(context)
    with pytest.raises(ValueError, match="^runtime-node-not-admitted$"):
        context.operations.container_exec("outside", ["true"], timeout=1)
    with pytest.raises(TypeError):
        context.environment["OTHER_KEY"] = "value"


def test_family_runtime_receives_trial_and_scoped_operations(family_input):
    from aptl.backends.scenario_family import FamilyTrialInput, admit_family_trial
    from aptl.backends.scenario_startup import (
        ScenarioStartupSelection,
        run_scenario_runtime,
    )

    bundle, family, plan = family_input()
    trial = admit_family_trial(
        bundle, BACKEND, FamilyTrialInput(plan, "entry-a", family)
    )
    seen = []

    class Provider:
        def realize_runtime(self, operations, nodes, *, trial):
            seen.append(trial.snapshot_digest)
            assert not hasattr(operations, "stop")
            assert nodes[0].name == "primary"
            return []

    selection = ScenarioStartupSelection(PACK, Provider(), None, trial=trial)
    assert (
        run_scenario_runtime(
            PACK, object(), (SimpleNamespace(name="primary"),), selection=selection
        )
        == []
    )
    assert seen == [trial.snapshot_digest]


def test_family_capture_resume_rejects_installation_drift(monkeypatch, family_input):
    from aptl.backends import scenario_family as contract
    from aptl.backends.scenario_capture import (
        ScenarioCaptureContribution,
        ScenarioCaptureResumeContext,
    )
    from aptl.backends.scenario_capture_discovery import (
        resolve_family_capture_resume,
        ScenarioCaptureProviderError,
    )

    bundle, family, plan = family_input()
    trial = contract.admit_family_trial(
        bundle, BACKEND, contract.FamilyTrialInput(plan, "entry-a", family)
    )
    provider = _provider(trial.target)
    provider.provider_id = "example-capture"
    provider.extension_api_version = "1"
    provider.resolve = lambda context: pytest.fail(
        "restart must use the resume contract"
    )
    observed = []

    def resume(context):
        assert not hasattr(context, "snapshot")
        observed.append(context.trial_identity["snapshot_digest"])
        return ScenarioCaptureContribution(())

    provider.resume_capture = resume
    entry = SimpleNamespace(
        name="example-family.aptl",
        load=lambda: provider,
        dist=SimpleNamespace(name="example-adapter", version="1.0"),
    )
    monkeypatch.setattr(contract.metadata, "entry_points", lambda **kw: [entry])
    context = ScenarioCaptureResumeContext(trial.target, trial.identity())
    selection = resolve_family_capture_resume(
        context, "example-adapter", "1.0", "example-capture"
    )
    assert selection.provider_id == "example-capture"
    assert observed == [trial.snapshot_digest]
    entry.dist.version = "2.0"
    with pytest.raises(
        ScenarioCaptureProviderError, match="^family-provider-installation-mismatch$"
    ):
        resolve_family_capture_resume(
            context, "example-adapter", "1.0", "example-capture"
        )
    assert len(observed) == 1


def test_capture_authority_restore_uses_safe_family_receipt(monkeypatch, family_input):
    from aptl.backends import scenario_family as contract
    from aptl.backends.raes_evidence_acquisition import _capture_selection_from_state

    bundle, family, plan = family_input()
    trial = contract.admit_family_trial(
        bundle, BACKEND, contract.FamilyTrialInput(plan, "entry-a", family)
    )
    adapter = {
        "pack_id": PACK.pack_id,
        "pack_version": PACK.pack_version,
        "pack_set_digest": PACK.set_digest,
        "backend_target_name": BACKEND.target_name,
        "backend_target_version": BACKEND.target_version,
        "backend_profile": BACKEND.profile,
        "backend_transport": BACKEND.transport,
        "provider_id": "example-capture",
        "distribution": "example-adapter",
        "distribution_version": "1.0",
        "entry_point": "example-family.aptl",
        "family": {
            "api_version": "1",
            "family_id": trial.target.family_id,
            "family_digest": trial.target.family_digest,
            "backend_provider": BACKEND.provider,
            "trial_identity": trial.identity(),
        },
    }
    restored = []

    def resume(context, distribution, version, provider_id):
        restored.append(context)
        return SimpleNamespace(
            provider_id=provider_id,
            distribution=distribution,
            distribution_version=version,
            entry_point="example-family.aptl",
        )

    monkeypatch.setattr(
        "aptl.backends.scenario_capture_discovery.resolve_family_capture_resume", resume
    )
    selected = _capture_selection_from_state({"capture_adapter": adapter})
    assert selected.provider_id == "example-capture"
    assert restored[0].target == trial.target
    assert restored[0].trial_identity == trial.identity()


def test_family_reset_receipt_preserves_target_and_rejects_wrong_pack(tmp_path):
    from aptl.backends.scenario_family import encode_family_target
    from aptl.core.startup_reset_state import (
        CleanupAction,
        persist_cleanup_action,
        load_pending_cleanup,
        ACTION_PACK_RESET,
    )

    encoded = encode_family_target(TARGET)
    action = CleanupAction(
        ACTION_PACK_RESET,
        "1",
        "admission-a",
        PACK.pack_id,
        PACK.pack_version,
        PACK.set_digest,
        "example-adapter",
        "1.0",
        PACK.pack_id,
        family_target=encoded,
    )
    persist_cleanup_action(tmp_path, action)
    pending, rejected = load_pending_cleanup(tmp_path)
    assert not rejected
    assert pending[0].action.family_target == encoded
    with pytest.raises(ValueError, match="invalid cleanup action"):
        persist_cleanup_action(tmp_path, replace(action, pack_version="2.0.0"))


def test_resume_context_rejects_extra_or_mismatched_trial_identity(family_input):
    from aptl.backends.scenario_family import FamilyTrialInput, admit_family_trial
    from aptl.backends.scenario_capture import ScenarioCaptureResumeContext

    bundle, family, plan = family_input()
    trial = admit_family_trial(
        bundle, BACKEND, FamilyTrialInput(plan, "entry-a", family)
    )
    for identity in (
        {**trial.identity(), "credential": "credential-canary"},
        {**trial.identity(), "family_digest": "sha256:" + "f" * 64},
    ):
        with pytest.raises(ValueError, match="^family-trial-identity-invalid$"):
            ScenarioCaptureResumeContext(trial.target, identity)


def test_trial_evidence_contains_provider_identity_without_snapshot_values(
    family_input,
):
    from aptl.backends.scenario_family import (
        FamilyTrialInput,
        admit_family_trial,
        FamilyProviderIdentity,
    )

    bundle, family, plan = family_input()
    trial = admit_family_trial(
        bundle, BACKEND, FamilyTrialInput(plan, "entry-a", family)
    )
    trial = replace(
        trial,
        providers=(
            FamilyProviderIdentity(
                "aptl.scenario_capture",
                "example-family.aptl",
                "example-provider",
                "example-adapter",
                "1.0",
                "1",
            ),
        ),
    )
    evidence = trial.evidence()
    assert evidence["providers"][0]["distribution"] == "example-adapter"
    assert evidence["trial"]["snapshot_digest"] == trial.snapshot_digest
    assert "/opt/a" not in str(evidence)


def test_family_start_rejects_wrong_archive_run_before_apply(monkeypatch, family_input):
    from aptl.backends import raes
    from aptl.backends.scenario_family import FamilyTrialInput, admit_family_trial
    from aptl.backends.raes_start_model import AcesRunTarget
    from aptl.core.config import AptlConfig

    bundle, family, plan = family_input()
    trial = admit_family_trial(
        bundle, BACKEND, FamilyTrialInput(plan, "entry-a", family)
    )
    admitted = SimpleNamespace(
        bundle=replace(bundle, trial=trial), target=object(), execution_plan=object()
    )
    monkeypatch.setattr(
        raes,
        "_apply_with_backend_retry",
        lambda *args: pytest.fail("must not apply with the wrong run identity"),
    )
    outcome = raes.start_raes_scenario(
        bundle.root,
        AptlConfig(),
        object(),
        scenario_path=bundle.sdl_path,
        admitted=admitted,
        run_target=AcesRunTarget(object(), "different-run"),
    )
    assert not outcome.lab_result.success
    assert "family-run-identity-mismatch" in outcome.lab_result.error


def test_family_runtime_failure_text_cannot_disclose_values(family_input):
    from aptl.backends.scenario_family import FamilyTrialInput, admit_family_trial
    from aptl.backends.scenario_startup import (
        ScenarioStartupSelection,
        run_scenario_runtime,
    )

    bundle, family, plan = family_input()
    trial = admit_family_trial(
        bundle, BACKEND, FamilyTrialInput(plan, "entry-a", family)
    )
    provider = SimpleNamespace(
        realize_runtime=lambda *args, **kw: ["credential-canary"]
    )
    selected = ScenarioStartupSelection(PACK, provider, None, trial=trial)
    assert run_scenario_runtime(PACK, object(), (), selection=selected) == [
        "family-runtime-failed"
    ]


def test_family_capture_sources_contain_callback_failures():
    from aptl.backends.scenario_capture import family_capture_sources

    request = SimpleNamespace(
        backend=object(),
        realization=SimpleNamespace(nodes=()),
        environment={},
        project_dir="private",
        capture_selection=SimpleNamespace(
            context=SimpleNamespace(trial=None),
            contribution=SimpleNamespace(
                runtime_environment_keys=(),
                native_registration_ids=frozenset({"example.events"}),
            ),
        ),
    )

    def broken(context):
        raise RuntimeError("credential-canary")

    request.capture_selection.contribution.runtime_adapter = SimpleNamespace(
        native_sources=broken
    )
    with pytest.raises(ValueError, match="^family-capture-sources-invalid$"):
        family_capture_sources(request)

    request.capture_selection.contribution.runtime_adapter.native_sources = (
        lambda context: {"ungranted.source": object()}
    )
    with pytest.raises(ValueError, match="^family-capture-sources-invalid$"):
        family_capture_sources(request)


def test_family_discovery_contains_metadata_failures(monkeypatch):
    from aptl.backends import scenario_family as contract

    def broken(**kwargs):
        raise RuntimeError("credential-canary")

    monkeypatch.setattr(contract.metadata, "entry_points", broken)
    with pytest.raises(ValueError, match="^family-provider-discovery-failed$"):
        contract.select_family_provider(
            "aptl.scenario_capture", "example-family.aptl", "1", "resolve", TARGET
        )


def test_retained_payload_validator_uses_recorded_family_installation(tmp_path):
    import json
    from aptl.core.evidence_bundle._collect import _validate_adapter_blob
    from aptl.core.evidence_bundle.limits import DEFAULT_LIMITS

    manifest = {
        "backend_evidence": {
            "pack_interaction": {
                "family_trial": {
                    "providers": [
                        {
                            "group": "aptl.scenario_capture",
                            "distribution": "example-adapter",
                            "distribution_version": "1.0",
                        }
                    ]
                }
            }
        }
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "payload.json").write_text("{}")
    calls = []
    expected = SimpleNamespace(
        dist=SimpleNamespace(name="example-adapter", version="1.0"),
        load=lambda: lambda payload: calls.append("expected"),
    )
    bundled = SimpleNamespace(
        dist=SimpleNamespace(name="lilrae", version="8.1"),
        load=lambda: lambda payload: pytest.fail("must not use bundled validator"),
    )
    assert _validate_adapter_blob(
        [expected, bundled], tmp_path, "payload.json", DEFAULT_LIMITS
    )
    assert calls == ["expected"]
    expected.dist.version = "2.0"
    assert not _validate_adapter_blob(
        [expected], tmp_path, "payload.json", DEFAULT_LIMITS
    )
    assert calls == ["expected"]


@pytest.mark.integration
@pytest.mark.parametrize("adapter_version", ["1.0.0", "2.1.0"])
def test_independent_wheels_use_only_public_contract(
    tmp_path, family_input, adapter_version
):
    import json
    import os
    from pathlib import Path
    import shutil
    import subprocess
    import sys
    from textwrap import dedent
    from aptl.backends.scenario_family import (
        FamilyTrialInput,
        admit_family_trial,
        encode_family_target,
    )

    repo = Path(__file__).resolve().parents[1]
    adapter = tmp_path / "adapter"
    shutil.copytree(repo / "tests/fixtures/family_adapter", adapter)
    metadata = adapter / "pyproject.toml"
    metadata.write_text(
        metadata.read_text().replace(
            'version = "1.0.0"', f'version = "{adapter_version}"'
        )
    )
    trials = []
    for value in ("/opt/a", "/opt/b"):
        bundle, family, plan = family_input(value, capture=True)
        trial = admit_family_trial(
            bundle, BACKEND, FamilyTrialInput(plan, "entry-a", family)
        )
        trials.append(
            {"snapshot": trial.snapshot.decode(), "digest": trial.snapshot_digest}
        )
    (adapter / "family_adapter/qualification.json").write_text(
        encode_family_target(trial.target)
    )
    (tmp_path / "trials.json").write_text(json.dumps(trials))

    def run(argv, cwd=tmp_path):
        result = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, timeout=180
        )
        assert result.returncode == 0, result.stdout + result.stderr

    for project, output in ((repo, "host-wheel"), (adapter, "adapter-wheel")):
        run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                str(tmp_path / output),
                str(project),
            ]
        )
    wheels = [
        str(next((tmp_path / output).glob("*.whl")))
        for output in ("host-wheel", "adapter-wheel")
    ]
    installed = tmp_path / "installed"
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--target",
            str(installed),
            *wheels,
        ]
    )
    script = dedent("""
        import json, sys
        from dataclasses import replace
        from pathlib import Path
        sys.path.insert(0, sys.argv[1])
        import aptl, family_adapter as adapter
        from aptl.backends.scenario_family import AdmittedFamilyTrial, require_family_capabilities
        from aptl.backends.pack_interaction import PackBackendInteractionContext
        from aptl.backends.pack_interaction_discovery import resolve_pack_backend_interaction
        from aptl.backends.scenario_capture import ScenarioCaptureContext
        from aptl.backends.scenario_capture_discovery import resolve_scenario_capture
        from aptl.backends.raes_evidence import admit_sdl_evidence
        from aptl.backends.raes_evidence_acquisition import NativeEvidenceRequest, acquire_native_evidence
        from aptl.core.evidence.outcomes import AcquisitionDisposition
        from aptl.core.runstore import LocalRunStore
        from types import SimpleNamespace
        from aptl.backends.scenario_planning_compatibility import ScenarioPlanningCompatibilityContext
        from aptl.backends.scenario_planning_compatibility_discovery import resolve_scenario_planning_compatibility
        from aptl.backends.scenario_startup import select_scenario_startup, run_scenario_runtime
        from aptl.core.scenario_bundle import ScenarioBundle, ScenarioSourceKind
        from aptl.validation.scenario_verification import ScenarioIdentity, VerificationContext, VerificationStatus
        from aptl.validation.scenario_verification_discovery import verify_scenario
        assert Path(aptl.__file__).is_relative_to(Path(sys.argv[1]))
        target = adapter.TARGET
        seen_digests = set()
        for value in json.loads(Path(sys.argv[2]).read_text()):
            trial = AdmittedFamilyTrial(target, value['digest'], value['snapshot'].encode())
            selections = require_family_capabilities(trial)
            assert len(selections) == 6
            assert {s.distribution for s in selections} == {'lilrae-family-contract-fixture'}
            assert {s.distribution_version for s in selections} == {sys.argv[3]}
            bundle = ScenarioBundle(target.pack.pack_id, Path.cwd(), Path('unused'), ScenarioSourceKind.ENV_PACK, target.pack, trial)
            startup = select_scenario_startup(bundle)
            assert run_scenario_runtime(target.pack, object(), (), selection=startup) == []
            assert resolve_pack_backend_interaction(PackBackendInteractionContext(target.pack, target.backend, ('nodes.primary',)), trial=trial).operator_groups == ('lab',)
            capture = resolve_scenario_capture(ScenarioCaptureContext(target.pack, target.backend, trial))
            capture_plan = admit_sdl_evidence(trial.scenario, registry=capture.registry)
            assert len(capture_plan.bindings) == 1
            store = LocalRunStore(Path.cwd() / ('store-' + trial.snapshot_digest[-8:]))
            acquired = acquire_native_evidence(NativeEvidenceRequest(
                capture_plan, object(), SimpleNamespace(nodes=()), Path.cwd(), {},
                store, trial.provenance.run_id, capture,
            ))
            assert acquired.disposition is AcquisitionDisposition.SEALED_READY
            assert len(acquired.records) == 1
            assert resolve_scenario_planning_compatibility(ScenarioPlanningCompatibilityContext(target.pack, target.backend, trial)) is not None
            scenario = ScenarioIdentity(target.family_id, target.family_digest, 'env-pack', target.pack.pack_version)
            report = verify_scenario(VerificationContext('run-a', 'attempt-a', scenario, target.backend, trial=trial))
            assert report.status is VerificationStatus.PASSED
            seen_digests.add(trial.snapshot_digest)
        assert len(seen_digests) == 2
        assert {item['snapshot_digest'] for item in adapter.SEEN} == seen_digests
        adapter.Provider.family_api_version = '2'
        try:
            require_family_capabilities(trial)
        except ValueError as exc:
            assert str(exc) == 'family-provider-metadata-invalid'
        else:
            raise AssertionError('unsupported family API accepted')
    """)
    run(
        [
            sys.executable,
            "-I",
            "-c",
            script,
            str(installed),
            str(tmp_path / "trials.json"),
            adapter_version,
        ]
    )
