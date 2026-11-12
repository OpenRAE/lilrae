"""Unchanged planning and native adapter evidence after bridge retirement."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from raes_contracts.runtime_state import RuntimeSnapshot
from raes_contracts.vocabulary import ObservationStrength
from raes_processor.semantics.realization import CONCERN_PAYLOAD_PATH

from aptl.backends._raes_planning_entry import AptlPlanningOptions
from aptl.backends._raes_runtime_capabilities import adapter_runtime_concern_sources
from aptl.backends.raes_manifest import create_aptl_manifest
from aptl.backends.raes_runtime import plan_for_target
from aptl.backends.scenario_startup import (
    ScenarioStartupSelection,
    observe_scenario_runtime_concerns,
)
from aptl.core.runtime_readback import ConcernReading
from aptl.core.scenario_bundle import PackIdentity


def test_planning_passes_the_identical_compiler_model_and_scope(monkeypatch):
    from aptl.backends import raes_runtime
    from raes_contracts.run_scope import PlanScope

    model = object()
    result = SimpleNamespace(diagnostics=[])
    compiler = MagicMock(return_value=model)
    planner = MagicMock(return_value=result)
    monkeypatch.setattr(raes_runtime, "compile_scenario_runtime_model", compiler)
    monkeypatch.setattr(raes_runtime, "plan", planner)
    manifest = create_aptl_manifest()
    target = SimpleNamespace(
        name="aptl", manifest=manifest, provisioner=SimpleNamespace(bundle=None)
    )
    scope = PlanScope(run_id="trial-run", instantiation_id="trial-entry")
    snapshot = RuntimeSnapshot()
    options = AptlPlanningOptions(
        snapshot=snapshot, parameters={"selected": "value"}, run_scope=scope
    )
    assert plan_for_target(target, "scenario", options) is result
    assert planner.call_args.args == (model, manifest, snapshot)
    assert planner.call_args.kwargs["scope"].run_id == "trial-run"
    assert planner.call_args.kwargs["scope"].instantiation_id == "trial-entry"
    assert compiler.call_args.kwargs["parameters"] == {"selected": "value"}


def test_runtime_apply_uses_released_limits_and_keeps_native_capture(monkeypatch):
    from aptl.backends.raes_runtime import AptlRuntimeManager, _RaesRuntimeManager
    from raes_runtime import backend_input_contracts, backend_snapshot_contracts

    before = (
        backend_input_contracts.RUNTIME_SNAPSHOT_VALUE_LIMITS,
        backend_snapshot_contracts._VALUE_LIMITS,
    )
    result = SimpleNamespace(snapshot=RuntimeSnapshot(), success=True)

    def apply(_self, _plan):
        assert before == (
            backend_input_contracts.RUNTIME_SNAPSHOT_VALUE_LIMITS,
            backend_snapshot_contracts._VALUE_LIMITS,
        )
        return result

    monkeypatch.setattr(_RaesRuntimeManager, "apply", apply)
    manager = object.__new__(AptlRuntimeManager)
    manager.native_evidence = MagicMock()
    plan = object()
    assert manager.apply(plan) is result
    manager.native_evidence.capture.assert_called_once_with(
        plan, result.snapshot, phase="initial", success=True
    )
    assert before == (
        backend_input_contracts.RUNTIME_SNAPSHOT_VALUE_LIMITS,
        backend_snapshot_contracts._VALUE_LIMITS,
    )


def _selection(reader, *, source=ObservationStrength.GUEST_OBSERVED):
    identity = PackIdentity("independent-family", "2.0.0", "sha256:" + "d" * 64)
    provider = SimpleNamespace(
        observed_runtime_concerns={"runtime-database-services": source},
        observe_runtime=reader,
    )
    return identity, ScenarioStartupSelection(identity, provider, None)


@pytest.mark.parametrize(
    "failure", ["undeclared", "wrong-source", "malformed", "oversized"]
)
def test_adapter_cannot_claim_unread_or_mislabelled_state(failure):
    kind = "runtime-database-services"
    source = (
        ObservationStrength.DAEMON_OBSERVED
        if failure == "wrong-source"
        else ObservationStrength.GUEST_OBSERVED
    )
    value = [{"database_service_id": "native", "engine": "postgresql"}]
    if failure == "malformed":
        value = {"unexpected": "shape"}
    elif failure == "oversized":
        value = ["large" * 500_000]
    reading = ConcernReading(kind, value, source)
    identity, selection = _selection(lambda *_: {CONCERN_PAYLOAD_PATH[kind]: reading})
    if failure == "undeclared":
        selection.provider.observed_runtime_concerns = {}
    assert (
        observe_scenario_runtime_concerns(
            identity, object(), object(), selection=selection
        )
        == {}
    )


def test_product_capability_requires_the_admitted_reader():
    kind = "runtime-database-services"
    default = create_aptl_manifest().realization_support[0]
    assert kind not in default.observation_capabilities
    identity, selection = _selection(lambda *_: {})
    sources = adapter_runtime_concern_sources(selection.provider)
    target = create_aptl_manifest(runtime_concern_sources=sources).realization_support[
        0
    ]
    assert (
        target.observation_capabilities[kind].observation_strength
        is ObservationStrength.GUEST_OBSERVED
    )
    rejected_input_1 = SimpleNamespace(
        observed_runtime_concerns={
            "runtime-environment": ObservationStrength.GUEST_OBSERVED
        },
        observe_runtime=lambda *_: {},
    )
    with pytest.raises(ValueError, match="source-conflict"):
        adapter_runtime_concern_sources(rejected_input_1)


@pytest.mark.parametrize("source", tuple(ObservationStrength))
@pytest.mark.parametrize(
    "kind", ["runtime-software-components", "runtime-environment"]
)
def test_image_software_reports_keep_their_declared_source(kind, source):
    provider = SimpleNamespace(
        observed_runtime_concerns={kind: source}, observe_runtime=lambda *_: {}
    )
    allowed = (
        {ObservationStrength.DRIVER_REPORTED, ObservationStrength.GUEST_OBSERVED}
        if kind == "runtime-software-components"
        else {ObservationStrength.DAEMON_OBSERVED}
    )
    if source not in allowed:
        with pytest.raises(ValueError):
            adapter_runtime_concern_sources(provider)
        return
    sources = adapter_runtime_concern_sources(provider)
    manifest = create_aptl_manifest(runtime_concern_sources=sources)
    assert manifest.realization_support[0].observation_capabilities[
        kind
    ].observation_strength is source
