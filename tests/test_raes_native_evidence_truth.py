"""Truth projection from admitted, sealed TechVault native evidence."""

from __future__ import annotations

from dataclasses import replace

import pytest

from raes_contracts.contracts import (
    ExperimentCaptureSpecReferenceModel,
    ExperimentChecksumModel,
    ExperimentEvidenceRecordModel,
    ExperimentReferenceModel,
)
from raes_contracts.contracts.experiment_capture import (
    ExperimentRawEvidenceContentModel,
)
from raes_contracts.planning import (
    ChangeAction,
    EvaluationOp,
    EvaluationPlan,
    OrchestrationPlan,
    ProvisioningPlan,
    RuntimeDomain,
)
from raes_contracts.runtime_state import OperationState, RuntimeSnapshot
from raes_processor.models import ExecutionPlan, RuntimeModel
from raes_backend_stubs.stubs import create_stub_target

from aptl.backends._raes_proposition_truth import (
    native_evidence_truth_is_complete as _native_evidence_truth_is_complete,
    project_proposition_truth_results as _project_proposition_truth_results,
)
from aptl.backends.raes_evaluator import AptlEvaluator, refresh_evidence_truth
from aptl_techvault.capture import TechVaultPropositionInterpreter

_INTERPRETER = TechVaultPropositionInterpreter()


def project_proposition_truth_results(*args, **kwargs):
    kwargs.setdefault("proposition_interpreter", _INTERPRETER)
    return _project_proposition_truth_results(*args, **kwargs)


def native_evidence_truth_is_complete(*args, **kwargs):
    kwargs.setdefault("proposition_interpreter", _INTERPRETER)
    return _native_evidence_truth_is_complete(*args, **kwargs)


def _record(
    requirement_id: str,
    *,
    evidence_kind: str = "log",
    channel_ref: str = "backend-log",
) -> ExperimentEvidenceRecordModel:
    digest = "ab" * 32
    return ExperimentEvidenceRecordModel(
        schema_version="experiment-evidence-record/v1",
        evidence_record_id=f"evidence-{requirement_id}",
        record_version="1.0.0",
        capture_spec_ref=ExperimentCaptureSpecReferenceModel(
            ref_kind="capture-spec",
            ref_id="techvault-capture",
        ),
        capture_requirement_ref=requirement_id,
        output_contract="experiment-evidence-record-v1",
        run_ref=ExperimentReferenceModel(ref_kind="run", ref_id="run-992"),
        source_refs=[
            ExperimentReferenceModel(
                ref_kind="measurement-channel",
                ref_id=channel_ref,
            )
        ],
        evidence_kind=evidence_kind,
        captured_at="2026-09-14T12:00:00Z",
        capture_window_ref="system_under_test",
        raw_content=ExperimentRawEvidenceContentModel(
            content_uri=f"evidence/blobs/{digest}",
            content_checksum=ExperimentChecksumModel(
                algorithm="sha256",
                value=digest,
            ),
            payload_summary="1 event retained",
            loss_disclosure=(
                "content withheld from participant projection; evaluator retains access"
            ),
        ),
        sensitivity="internal",
        redaction_state="withheld",
        redaction_policy="aptl.evaluator-only-withholding/v1",
    )


def _plan(
    requirement_id: str = "suricata-local-rule-readiness",
    *,
    property_name: str = "network-detection-rule-source-ready",
    semantic_ref: str = "urn:raes:observable:network-detection-rule-source-ready",
    evidence_channel: str = "log",
) -> EvaluationPlan:
    proposition_address = "evaluation.proposition.suricata-local-rules-ready"
    assertion_address = "evaluation.assertion.suricata-local-rules-ready"
    return EvaluationPlan(
        operations=[
            EvaluationOp(
                action=ChangeAction.CREATE,
                address=proposition_address,
                resource_type="proposition",
                payload={
                    "name": "suricata-local-rules-ready",
                    "spec": {
                        "predicate": {
                            "kind": "boolean",
                            "property": property_name,
                            "semantic_ref": semantic_ref,
                            "operator": "equals",
                            "expected": True,
                        }
                    },
                    "subject_addresses": (),
                    "predicate_kind": "boolean",
                    "quantifier": "all",
                    "evaluation_basis": "observed_state",
                    "evidence_requirement_refs": (requirement_id,),
                    "evidence_channels": (evidence_channel,),
                    "unresolved_evidence_channel_refs": (),
                    "required_time_domain": "scenario_time",
                },
            ),
            EvaluationOp(
                action=ChangeAction.CREATE,
                address=assertion_address,
                resource_type="assertion",
                payload={
                    "name": "suricata-local-rules-ready",
                    "proposition_address": proposition_address,
                    "role": "postcondition",
                    "polarity": "positive",
                },
            ),
        ]
    )


def test_sealed_native_record_decides_only_its_exact_techvault_proposition():
    result = project_proposition_truth_results(
        _plan(),
        RuntimeSnapshot(),
        evidence_records=(_record("suricata-local-rule-readiness"),),
    )

    truth = result["evaluation.assertion.suricata-local-rules-ready"]
    assert truth["proposition_outcome"] == "true"
    assert truth["assertion_outcome"] == "true"
    assert truth["evidence_refs"] == ["evidence-suricata-local-rule-readiness"]
    assert truth["probe_binding"]["artifact_digest"] == "sha256:" + "ab" * 32
    assert truth["temporal_context"]["boundary_ref"] == "system_under_test"


@pytest.mark.parametrize(
    (
        "requirement_id",
        "property_name",
        "semantic_ref",
        "evidence_channel",
        "evidence_kind",
        "record_channel",
    ),
    [
        (
            "suricata-local-rule-readiness",
            "network-detection-rule-source-ready",
            "urn:raes:observable:network-detection-rule-source-ready",
            "log",
            "log",
            "backend-log",
        ),
        (
            "suricata-login-sqli-alert",
            "network-detection-alert-sid-1000010-observed",
            "urn:raes:observable:network-detection-alert-observed",
            "log",
            "log",
            "backend-log",
        ),
    ],
)
def test_each_exact_techvault_native_requirement_has_a_truth_binding(
    requirement_id,
    property_name,
    semantic_ref,
    evidence_channel,
    evidence_kind,
    record_channel,
):
    result = project_proposition_truth_results(
        _plan(
            requirement_id,
            property_name=property_name,
            semantic_ref=semantic_ref,
            evidence_channel=evidence_channel,
        ),
        RuntimeSnapshot(),
        evidence_records=(
            _record(
                requirement_id,
                evidence_kind=evidence_kind,
                channel_ref=record_channel,
            ),
        ),
    )

    assert len(result) == 1


def test_native_record_does_not_decide_a_mismatched_predicate():
    result = project_proposition_truth_results(
        _plan(property_name="some-other-property"),
        RuntimeSnapshot(),
        evidence_records=(_record("suricata-local-rule-readiness"),),
    )

    assert result == {}


def test_native_record_does_not_decide_a_mismatched_record_channel():
    result = project_proposition_truth_results(
        _plan(),
        RuntimeSnapshot(),
        evidence_records=(
            _record(
                "suricata-local-rule-readiness",
                evidence_kind="observation",
                channel_ref="participant-observation",
            ),
        ),
    )

    assert result == {}


def test_evaluator_projects_bound_native_evidence_into_runtime_snapshot():
    evaluator = AptlEvaluator(proposition_interpreter=_INTERPRETER)
    evaluator.bind_evidence_records((_record("suricata-local-rule-readiness"),))

    result = evaluator.start(_plan(), RuntimeSnapshot())

    assert result.success is True
    assert sorted(result.snapshot.proposition_truth_results) == [
        "evaluation.assertion.suricata-local-rules-ready"
    ]


class _OneRuntime:
    """The run's one runtime, reduced to the evaluation contract lilrae uses.

    ``evaluate`` runs the real APTL evaluator, so truth comes from the bound
    records; RAES's own evaluation replanning is RAES's to test.
    """

    def __init__(self, target, *, state=OperationState.SUCCEEDED):
        self._target = target
        self._state = state
        self.snapshot = RuntimeSnapshot()
        self.keys: list[str] = []

    def evaluate(self, execution_plan, *, idempotency_key=""):
        from types import SimpleNamespace

        self.keys.append(idempotency_key)
        result = self._target.evaluator.start(execution_plan.evaluation, self.snapshot)
        self.snapshot = result.snapshot
        return SimpleNamespace(accepted=True, operation_id="evaluation-1", diagnostics=())

    def get_operation(self, operation_id):
        from types import SimpleNamespace

        return SimpleNamespace(state=self._state, diagnostics=())


def _execution_plan(target, evaluation=None):
    return ExecutionPlan(
        target_name=target.name,
        manifest=target.manifest,
        base_snapshot=RuntimeSnapshot(),
        scenario_name="native-evidence-refresh",
        model=RuntimeModel(scenario_name="native-evidence-refresh"),
        provisioning=ProvisioningPlan(),
        orchestration=OrchestrationPlan(),
        evaluation=evaluation or _plan(),
        observation_owner=RuntimeDomain.PROVISIONING,
    )


def _evaluator_target():
    return replace(
        create_stub_target(),
        evaluator=AptlEvaluator(proposition_interpreter=_INTERPRETER),
    )


def test_native_evidence_is_evaluated_by_the_runs_one_runtime():
    """The runtime that applied the plan evaluates the evidence (rae#1660)."""

    target = _evaluator_target()
    runtime = _OneRuntime(target)

    refresh = refresh_evidence_truth(
        target=target,
        execution_plan=_execution_plan(target),
        snapshot=RuntimeSnapshot(),
        evidence_records=(_record("suricata-local-rule-readiness"),),
        runtime_manager=runtime,
    )

    assert refresh.status is OperationState.SUCCEEDED
    assert refresh.snapshot is runtime.snapshot
    assert sorted(refresh.snapshot.proposition_truth_results) == [
        "evaluation.assertion.suricata-local-rules-ready"
    ]


def test_each_evidence_collection_gets_its_own_evaluation_key():
    """RAES treats a reused key as a retry of the same evaluation request."""

    target = _evaluator_target()
    runtime = _OneRuntime(target)
    plan = _execution_plan(target)
    first = (_record("suricata-local-rule-readiness"),)
    second = (_record("suricata-local-rule-readiness", channel_ref="other-log"),)

    for records in (first, first, second):
        refresh_evidence_truth(
            target=target,
            execution_plan=plan,
            snapshot=RuntimeSnapshot(),
            evidence_records=records,
            runtime_manager=runtime,
        )

    assert runtime.keys[0] == runtime.keys[1]
    assert runtime.keys[0] != runtime.keys[2]


def test_native_evidence_is_not_evaluated_without_the_runs_runtime():
    """No second runtime owner is created when the run's runtime is absent."""

    target = _evaluator_target()

    refresh = refresh_evidence_truth(
        target=target,
        execution_plan=_execution_plan(target),
        snapshot=RuntimeSnapshot(),
        evidence_records=(_record("suricata-local-rule-readiness"),),
    )

    assert refresh.status is OperationState.FAILED
    assert [diagnostic.code for diagnostic in refresh.diagnostics] == [
        "aptl.evaluator.native-evidence-refresh-unavailable"
    ]


def test_lab_refresh_uses_the_apply_runtime_and_adopts_its_snapshot(tmp_path):
    from types import SimpleNamespace

    from aptl.core.lab import _LabStartContext, _refresh_required_native_evidence

    target = _evaluator_target()
    runtime = _OneRuntime(target)
    execution_plan = _execution_plan(target)
    outcome = SimpleNamespace(final_snapshot=RuntimeSnapshot(), runtime_manager=runtime)
    context = _LabStartContext(
        project_dir=tmp_path,
        skip_seed=False,
        admitted_start=SimpleNamespace(target=target, execution_plan=execution_plan),
        raes_outcome=outcome,
    )

    failure = _refresh_required_native_evidence(
        context,
        context.admitted_start,
        (_record("suricata-local-rule-readiness"),),
    )

    assert failure is None
    assert runtime.keys
    assert outcome.final_snapshot is runtime.snapshot


def test_native_evidence_refresh_fails_when_the_authored_predicate_does_not_match():
    target = _evaluator_target()

    refresh = refresh_evidence_truth(
        target=target,
        execution_plan=_execution_plan(
            target, _plan(property_name="some-other-property")
        ),
        snapshot=RuntimeSnapshot(),
        evidence_records=(_record("suricata-local-rule-readiness"),),
        runtime_manager=_OneRuntime(target),
    )

    assert refresh.status is OperationState.FAILED
    assert [diagnostic.code for diagnostic in refresh.diagnostics] == [
        "aptl.evaluator.native-evidence-truth-incomplete"
    ]


@pytest.mark.parametrize("record_count", [0, 2], ids=("missing", "duplicate"))
def test_native_evidence_truth_requires_one_bound_record_per_requirement(record_count):
    plan = _plan()
    record = _record("suricata-local-rule-readiness")
    projected = project_proposition_truth_results(
        plan,
        RuntimeSnapshot(),
        evidence_records=(record,),
    )
    snapshot = RuntimeSnapshot(proposition_truth_results=projected)

    assert not native_evidence_truth_is_complete(
        plan,
        snapshot,
        (record,) * record_count,
    )



_REFRESH_SDL = """\
name: native-refresh
description: One node and one native evidence proposition.
nodes:
  sensor:
    type: compute
propositions:
  suricata-local-rules-ready:
    description: The sensor reports its local rule source ready.
    subjects: [nodes.sensor]
    basis: observed_state
    predicate:
      kind: boolean
      property: network-detection-rule-source-ready
      semantic_ref: urn:raes:observable:network-detection-rule-source-ready
      expected: true
    evidence_requirements: [suricata-local-rule-readiness]
assertions:
  suricata-local-rules-ready:
    proposition: suricata-local-rules-ready
    role: postcondition
evidence_requirements:
  suricata-local-rule-readiness:
    description: Records the sensor rule readiness result.
    source_refs: [nodes.sensor]
    scope_refs: [nodes.sensor]
    scope: Sensor rule readiness.
    boundary_kind: system_under_test
    channel: log
    artifact_role: network_detection_rule_readiness
    sensitivity: plain
    redaction: redact_sensitive
    integrity: checksum
    retention: run_lifetime
    loss_disclosure: required
"""


def _refresh_target():
    """Return a stub target that offers the released rule-readiness capture."""
    from aptl.backends.raes_manifest import create_aptl_manifest
    from tests.test_raes_evidence import _registry

    stub = create_stub_target()
    observation = create_aptl_manifest(_registry()).observation
    offer = next(
        item
        for item in observation.capture_offers
        if item.offer_id == "aptl.collector.suricata-rule-readiness"
    )
    # Bind the released offer to the one-node scenario's refs and scope.
    offer = replace(
        offer,
        source_refs=frozenset({"nodes.sensor"}),
        scope_refs=frozenset({"nodes.sensor"}),
        scopes=frozenset({"Sensor rule readiness."}),
    )
    capabilities = replace(
        stub.manifest.capabilities,
        observation=replace(observation, capture_offers=(offer,)),
    )
    return replace(
        stub,
        manifest=replace(stub.manifest, capabilities=capabilities),
        evaluator=AptlEvaluator(proposition_interpreter=_INTERPRETER),
    )


def test_refresh_commits_truth_through_the_run_runtime_that_applied(tmp_path):
    """Plan, apply, then refresh native evidence on that same runtime (#1407)."""
    from types import SimpleNamespace

    from raes import parse_sdl_file

    from aptl.backends.raes_planning_compat import AptlRuntimeManager
    from aptl.core.lab import _refresh_required_native_evidence

    scenario = tmp_path / "refresh.sdl.yaml"
    scenario.write_text(_REFRESH_SDL, encoding="utf-8")
    target = _refresh_target()
    with AptlRuntimeManager(target) as manager:
        execution_plan = manager.plan(parse_sdl_file(scenario))
        assert execution_plan.is_valid, execution_plan.diagnostics
        applied = manager.apply(execution_plan)
        assert applied.success, applied.diagnostics
        applied_entries = manager.snapshot.entries
        outcome = SimpleNamespace(
            runtime_manager=manager, final_snapshot=manager.snapshot
        )

        failure = _refresh_required_native_evidence(
            SimpleNamespace(raes_outcome=outcome),
            SimpleNamespace(target=target, execution_plan=execution_plan),
            (_record("suricata-local-rule-readiness"),),
        )

        assert failure is None
        assert outcome.final_snapshot == manager.snapshot
        assert manager.snapshot.entries == applied_entries
        assert manager.snapshot.proposition_truth_results[
            "evaluation.assertion.suricata-local-rules-ready"
        ]["assertion_outcome"] == "true"
