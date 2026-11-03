"""Required trial observations gate the real RAES delivery boundary."""

import json
from dataclasses import replace
from decimal import Decimal
from threading import Event
from time import monotonic
from types import SimpleNamespace

import pytest
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_contracts.trial_unit import TrialUnitRequest
from raes_processor.trial_realization import realize_admitted_trial_entry
from raes_runtime import RuntimeControlPlane
from raes_runtime.registry_probes import sample_participant_action_admission_request

from aptl.backends.readiness import ReadinessEnvironment, TrialReadiness
from aptl.core.correlation.clock import FixedClockProvider
from aptl.core.experiment.capture_plan import admit_capture_demands
from aptl.core.experiment.capture_registry import CollectorRegistry
from aptl.core.runstore import LocalRunStore
from aptl.core.trial_readiness import ReadinessOwners
from tests.cleanup_runtime_fixture import Services, runtime_inputs, target_for
from tests.test_experiment_capture_mapping import _covering_registration
from tests.test_trial_serving import SchedulerDelivery, finish, serving
from tests.trial_readiness_fixture import readiness_for


@pytest.fixture
def admitted(tmp_path):
    inputs, manifest = runtime_inputs(tmp_path)
    target = target_for(manifest)
    services = Services(tmp_path)
    with RuntimeControlPlane(target) as runtime:
        experiment_id = runtime.admit_experiment(inputs, services=services)
        delivery = SchedulerDelivery(runtime, experiment_id)
        cleanup = services.cleanups[delivery.request.execution_attempt_id]
        yield inputs, target, delivery, cleanup


def test_missing_required_owner_blocks_and_retains_safe_results(tmp_path, admitted):
    inputs, target, delivery, cleanup = admitted
    gate = TrialReadiness(
        inputs,
        ReadinessEnvironment(
            target=target,
            artifact_probe=None,
            scenario_root=tmp_path / "pack",
            store=cleanup.store,
            clock=cleanup.clock,
            owners=ReadinessOwners(),
        ),
    )
    with pytest.raises(ValueError, match="trial-readiness-blocked"):
        gate.prepare(delivery.request)
    assert delivery.calls == 0
    results = list(
        cleanup.store.get_run_path(delivery.request.run_id).glob("readiness/*/*.json")
    )
    assert results
    payload = json.loads(results[-1].read_text())
    assert payload["execution_attempt_id"] == delivery.request.execution_attempt_id
    assert payload["plan_digest"] == delivery.request.plan.plan_digest
    assert any(item["severity"] == "error" for item in payload["checks"])


def test_owner_failure_is_not_rendered_as_a_secret(tmp_path, admitted):
    inputs, target, delivery, cleanup = admitted

    def crash():
        raise RuntimeError("password=operator-private-value")

    gate = TrialReadiness(
        inputs,
        ReadinessEnvironment(
            target=target,
            artifact_probe=None,
            scenario_root=tmp_path / "pack",
            store=cleanup.store,
            clock=cleanup.clock,
            owners=ReadinessOwners(containment=crash),
        ),
    )
    with pytest.raises(ValueError, match="^trial-readiness-blocked$"):
        gate.prepare(delivery.request)
    for path in cleanup.store.get_run_path(delivery.request.run_id).glob(
        "readiness/*/*.json"
    ):
        assert "operator-private-value" not in path.read_text()


def test_readiness_does_not_accept_a_substituted_snapshot(tmp_path, admitted):
    inputs, target, delivery, cleanup = admitted
    gate = TrialReadiness(
        inputs,
        ReadinessEnvironment(
            target=target,
            artifact_probe=None,
            scenario_root=tmp_path / "pack",
            store=cleanup.store,
            clock=cleanup.clock,
            owners=ReadinessOwners(containment=lambda: True),
        ),
    )
    wrong = replace(delivery.request, instantiated_sdl_digest="sha256:" + "f" * 64)
    with pytest.raises(ValueError, match="trial-readiness-blocked"):
        gate.prepare(wrong)
    assert delivery.calls == 0


@pytest.mark.parametrize("name", ["orchestrator", "evaluator"])
def test_effect_adapter_refuses_before_starting_work(admitted, name):
    inputs, target, delivery, _ = admitted
    realized = realize_admitted_trial_entry(
        inputs=inputs, plan_entry_id=delivery.request.plan_entry_id
    )

    class Refusal:
        def require_live(self):
            raise ValueError("required-source-unavailable")

    component = getattr(target, name)
    component.readiness = Refusal()
    plan = getattr(
        realized.execution_plan,
        "orchestration" if name == "orchestrator" else "evaluation",
    )
    with pytest.raises(ValueError, match="^required-source-unavailable$"):
        component.start(plan, RuntimeSnapshot())


def test_exact_admitted_entry_passes_with_its_installed_owners(tmp_path, admitted):
    inputs, target, delivery, cleanup = admitted
    gate = readiness_for(inputs, target, cleanup.store, cleanup.clock, tmp_path)
    try:
        gate.record_clean(delivery.request, lambda: None)
        gate.prepare(delivery.request)
        gate.check_live()
        assert gate.references
        for reference in gate.references:
            payload = cleanup.store.read_run_json(delivery.request.run_id, reference)
            assert all(check["severity"] == "info" for check in payload["checks"])
    finally:
        gate.close()


def test_trial_wrapper_requires_readiness_before_dispatch(tmp_path):
    with serving(tmp_path) as (handler, request, *_):
        handler = replace(handler, readiness=None)
        with pytest.raises(ValueError, match="^trial-readiness-unavailable$"):
            handler.execute_trial(request)
        assert handler.runtime_unit.calls == 0


def test_capture_spec_binding_uses_the_selected_collectors_channel(admitted):
    inputs, target, delivery, _ = admitted
    realized = realize_admitted_trial_entry(
        inputs=inputs, plan_entry_id=delivery.request.plan_entry_id
    )
    registration = _covering_registration(
        capture_offer=target.manifest.observation.capture_offers[0]
    )
    plan = admit_capture_demands(
        realized.execution_plan.model.capture_demands,
        source_identity=realized.snapshot_digest,
        registry=CollectorRegistry((registration,)),
    )
    bindings = plan.runtime_bindings()
    assert bindings
    assert all(item.channel_kind == registration.channel_kind for item in bindings)


@pytest.mark.parametrize("result", [False, None, 1, {"passed": True}])
def test_truthy_or_missing_check_results_never_authorize_work(
    tmp_path, admitted, result
):
    inputs, target, delivery, cleanup = admitted
    gate = readiness_for(
        inputs,
        target,
        cleanup.store,
        cleanup.clock,
        tmp_path,
        owners={"containment": lambda: result},
    )
    try:
        with pytest.raises(ValueError, match="^trial-readiness-blocked$"):
            gate.prepare(delivery.request)
        assert delivery.calls == 0
    finally:
        gate.close()


@pytest.mark.parametrize(
    "failure", ["collector", "source", "destination", "service", "provider"]
)
def test_a_required_owner_failure_blocks_the_affected_trial(
    tmp_path, admitted, failure
):
    inputs, target, delivery, cleanup = admitted
    gate = readiness_for(inputs, target, cleanup.store, cleanup.clock, tmp_path)
    selected = gate.owners
    if failure == "provider":
        selected = replace(
            selected,
            participants=(replace(selected.participants[0], check=lambda: False),),
        )
    elif failure == "service":
        selected = replace(selected, services=lambda scenario: False)
    elif failure == "collector":
        selected = replace(selected, captures={})
    else:
        key, source = next(iter(selected.captures.items()))
        if failure == "source":
            source = replace(source, check=lambda binding: False)
        else:
            source = replace(
                source,
                destination=replace(source.destination, check=lambda required: False),
            )
        selected = replace(selected, captures={key: source})
    gate.owners = selected
    try:
        gate.record_clean(delivery.request, lambda: None)
        with pytest.raises(ValueError, match="^trial-readiness-blocked$"):
            gate.prepare(delivery.request)
            gate.check_live()
        assert delivery.calls == 0
        assert any(
            check["severity"] == "error"
            for ref in gate.references
            for check in cleanup.store.read_run_json(delivery.request.run_id, ref)[
                "checks"
            ]
        )
    finally:
        gate.close()


def test_insufficient_run_filesystem_space_blocks_before_dispatch(
    tmp_path, admitted, monkeypatch
):
    inputs, target, delivery, cleanup = admitted
    gate = readiness_for(inputs, target, cleanup.store, cleanup.clock, tmp_path)
    monkeypatch.setattr(
        "aptl.backends.readiness.os.fstatvfs",
        lambda fd: SimpleNamespace(f_bavail=0, f_frsize=4096),
    )
    try:
        with pytest.raises(ValueError, match="^trial-readiness-blocked$"):
            gate.prepare(delivery.request)
        assert delivery.calls == 0
        assert any(
            "storage.failed" in check["code"]
            for ref in gate.references
            for check in cleanup.store.read_run_json(delivery.request.run_id, ref)[
                "checks"
            ]
        )
    finally:
        gate.close()


@pytest.mark.parametrize(
    "offset,uncertainty,synchronized,limit,passes",
    [
        (None, None, "unknown", None, True),
        (None, None, "unknown", Decimal(5), False),
        ("3ms", "1ms", "synchronized", Decimal(5), True),
        ("0.01s", "1ms", "synchronized", Decimal(5), False),
        ("1ms", "-1ms", "synchronized", Decimal(5), False),
        ("1", "1", "synchronized", Decimal(5), False),
    ],
)
def test_clock_accuracy_is_a_selected_source_obligation(
    tmp_path, admitted, offset, uncertainty, synchronized, limit, passes
):
    inputs, target, delivery, cleanup = admitted
    gate = readiness_for(inputs, target, cleanup.store, cleanup.clock, tmp_path)
    gate.registry = CollectorRegistry(
        tuple(
            replace(item, clock_accuracy_ms=None if limit is None else int(limit))
            for item in gate.registry.registrations
        )
    )
    key, source = next(iter(gate.owners.captures.items()))
    source = replace(
        source,
        clock=FixedClockProvider(
            measurement_time=cleanup.clock.now(),
            measured_offset=offset,
            uncertainty=uncertainty,
            synchronization_status=synchronized,
        ),
    )
    gate.owners = replace(gate.owners, captures={key: source})
    try:
        gate.record_clean(delivery.request, lambda: None)
        gate.prepare(delivery.request)
        if passes:
            gate.check_live()
        else:
            with pytest.raises(ValueError, match="^trial-readiness-blocked$"):
                gate.check_live()
    finally:
        gate.close()


def test_a_required_capture_clock_cannot_be_omitted(tmp_path, admitted):
    inputs, target, delivery, cleanup = admitted
    gate = readiness_for(inputs, target, cleanup.store, cleanup.clock, tmp_path)
    gate.registry = CollectorRegistry(
        tuple(
            replace(item, clock_accuracy_ms=10) for item in gate.registry.registrations
        )
    )
    try:
        gate.record_clean(delivery.request, lambda: None)
        gate.prepare(delivery.request)
        with pytest.raises(ValueError, match="^trial-readiness-blocked$"):
            gate.check_live()
        assert not gate.execution_ready
        assert any(
            check["code"].endswith("clock.failed")
            for ref in gate.references
            for check in cleanup.store.read_run_json(delivery.request.run_id, ref)[
                "checks"
            ]
        )
    finally:
        gate.close()


def test_results_are_immutable_and_cannot_authorize_unowned_effects(tmp_path, admitted):
    inputs, target, delivery, cleanup = admitted
    gate = readiness_for(inputs, target, cleanup.store, cleanup.clock, tmp_path)
    try:
        gate.record_clean(delivery.request, lambda: None)
        gate.prepare(delivery.request)
        gate.check_live()
        original = {
            ref: (
                cleanup.store.get_run_path(delivery.request.run_id) / ref
            ).read_bytes()
            for ref in gate.references
        }
        with pytest.raises(ValueError, match="^trial-readiness-placement-unowned$"):
            gate.require_live()
        gate.check_live()
        assert set(original) == set(gate.references)
        for ref, raw in original.items():
            assert (
                cleanup.store.get_run_path(delivery.request.run_id) / ref
            ).read_bytes() == raw
    finally:
        gate.close()


def test_unselected_resource_checks_are_not_run(tmp_path, admitted):
    inputs, target, delivery, cleanup = admitted

    def unexpected(scenario):
        pytest.fail("the control entry did not require this resource check")

    gate = readiness_for(
        inputs,
        target,
        cleanup.store,
        cleanup.clock,
        tmp_path,
        owners={"resources": unexpected},
    )
    try:
        gate.record_clean(delivery.request, lambda: None)
        gate.prepare(delivery.request)
        gate.check_live()
    finally:
        gate.close()


def test_failed_live_readiness_cannot_return_a_successful_trial(tmp_path):
    with serving(tmp_path) as (handler, request, services, *_):
        handler.readiness.owners = replace(
            handler.readiness.owners, services=lambda scenario: False
        )
        result = finish(handler, request)
        assert result.cleanup_receipt.trial_outcome != "succeeded"
        assert services.events.count("cleanup") == 1


@pytest.mark.parametrize("sealed", [False, True])
def test_persistence_refusal_blocks_with_a_safe_error(
    tmp_path, admitted, monkeypatch, sealed
):
    inputs, target, delivery, cleanup = admitted
    gate = readiness_for(inputs, target, cleanup.store, cleanup.clock, tmp_path)
    if sealed:
        cleanup.store.commit_seal_marker(delivery.request.run_id, {"sealed": True})
    else:

        def denied(*args):
            raise OSError("password=storage-private-value")

        monkeypatch.setattr(cleanup.store, "create_run_json_once", denied)
    try:
        with pytest.raises(ValueError, match="^trial-readiness-storage-unavailable$"):
            gate.prepare(delivery.request)
        assert delivery.calls == 0
        assert not gate.references
    finally:
        gate.close()


def test_a_new_attempt_cannot_reuse_prepared_readiness(tmp_path, admitted):
    inputs, target, delivery, cleanup = admitted
    gate = readiness_for(inputs, target, cleanup.store, cleanup.clock, tmp_path)
    try:
        gate.prepare(delivery.request)
        other = replace(delivery.request, execution_attempt_id="different-attempt")
        with pytest.raises(ValueError, match="^trial-readiness-request-changed$"):
            gate.prepare(other)
    finally:
        gate.close()


def test_fixed_control_runs_without_the_final_crossed_matrix_or_cloud(tmp_path):
    with serving(tmp_path, control_only=True) as (handler, request, *_):
        assert len(request.plan.entries) == 1
        result = finish(handler, request)
        assert result.cleanup_receipt.trial_outcome == "succeeded"
        handoff = handler.cleanup.store.read_run_json(
            request.run_id, "trial-serving/handoff.json"
        )
        assert handoff["readiness_refs"]


def test_missing_pinned_artifact_blocks_without_remote_lookup(tmp_path):
    inputs, manifest = runtime_inputs(tmp_path, required_artifact=True)
    entry_id = next(iter(inputs.plan.entries))
    from raes_processor.trial_realization import instantiate_admitted_trial_entry

    from aptl.backends.raes_artifact_availability import (
        artifact_availability_for_scenario,
    )

    class Probe:
        def __init__(self, available):
            self.available, self.calls = available, []

        def artifact_available(self, reference, *, allow_remote):
            self.calls.append((reference, allow_remote))
            return self.available

    present = Probe(True)
    scenario = instantiate_admitted_trial_entry(
        plan=inputs.plan, plan_entry_id=entry_id, family=inputs.family
    )
    availability = artifact_availability_for_scenario(
        scenario, present, allow_remote=False
    )
    realized = realize_admitted_trial_entry(
        inputs=inputs, plan_entry_id=entry_id, artifact_availability=availability
    )
    request = TrialUnitRequest(
        plan=inputs.plan,
        plan_entry_id=entry_id,
        execution_attempt_id="attempt-image",
        instantiated_sdl_digest=realized.snapshot_digest,
        provisioning_plan=realized.provisioning_plan,
        orchestration_plan=realized.orchestration_plan,
        evaluation_plan=realized.evaluation_plan,
    )
    missing = Probe(False)
    store = LocalRunStore(tmp_path / "runs")
    gate = readiness_for(
        inputs,
        target_for(manifest),
        store,
        FixedClockProvider(measurement_time="2026-11-01T10:00:00Z"),
        tmp_path,
        artifact_probe=missing,
    )
    try:
        with pytest.raises(ValueError, match="^trial-readiness-blocked$"):
            gate.prepare(request)
        assert missing.calls and all(remote is False for _, remote in missing.calls)
    finally:
        gate.close()


def test_timeout_retains_a_failed_result_and_never_becomes_a_late_pass(
    tmp_path, admitted
):
    inputs, target, delivery, cleanup = admitted
    release = Event()
    gate = readiness_for(
        inputs, target, cleanup.store, cleanup.clock, tmp_path, probe_timeout_ms=5000
    )
    try:
        gate.record_clean(delivery.request, lambda: None)
        gate.prepare(delivery.request)
        gate.owners = replace(gate.owners, services=lambda scenario: release.wait())
        started = monotonic()
        with pytest.raises(ValueError, match="^trial-readiness-blocked$"):
            gate.check_live()
        assert monotonic() - started < 8
        assert gate.has_pending_probes
        assert not gate.execution_ready
        assert any(
            check["code"].endswith("services.timeout")
            for ref in gate.references
            for check in cleanup.store.read_run_json(delivery.request.run_id, ref)[
                "checks"
            ]
        )
    finally:
        release.set()
        gate.close()
    assert not gate.execution_ready


def test_participant_admission_cannot_bypass_a_required_live_refusal(admitted):
    _inputs, target, _delivery, _cleanup = admitted

    class Refusal:
        def require_live(self):
            raise ValueError("required-source-unavailable")

    target.participant_runtime.readiness = Refusal()
    request = sample_participant_action_admission_request()
    with pytest.raises(ValueError, match="^required-source-unavailable$"):
        target.participant_runtime.admit_action(request, RuntimeSnapshot())


def test_readiness_results_cannot_follow_a_store_symlink(tmp_path, admitted):
    inputs, target, delivery, cleanup = admitted
    root = cleanup.store.get_run_path(delivery.request.run_id)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "readiness").symlink_to(outside, target_is_directory=True)
    gate = readiness_for(inputs, target, cleanup.store, cleanup.clock, tmp_path)
    try:
        with pytest.raises(ValueError, match="^trial-readiness-storage-unavailable$"):
            gate.prepare(delivery.request)
        assert list(outside.iterdir()) == []
        assert delivery.calls == 0
    finally:
        gate.close()


def test_next_entry_rechecks_its_configuration_after_verified_cleanup(tmp_path):
    with serving(tmp_path) as (handler, request, services, runtime, experiment_id):
        assert finish(handler, request).cleanup_receipt.trial_outcome == "succeeded"
        first = handler.cleanup.store.read_run_json(
            request.run_id, "trial-serving/handoff.json"
        )
        initial = [
            item.configuration_digest for item in request.participant_configurations
        ]
        next_index = next(
            index
            for index, entry in enumerate(request.plan.entries.values())
            if [item.configuration_digest for item in entry.participant_configurations]
            != initial
        )
        delivery = SchedulerDelivery(runtime, experiment_id, entry_index=next_index)
        second_request = delivery.request
        second = replace(
            handler,
            runtime_unit=delivery,
            cleanup=services.cleanups[second_request.execution_attempt_id],
            target_scope=delivery.unit.run._target_scope,
        )
        # The installed participant still has the first entry's settings.
        with pytest.raises(ValueError, match="^trial-readiness-blocked$"):
            second.execute_trial(second_request)
        assert delivery.calls == 0
        assert (
            handler.cleanup.store.read_run_json(
                request.run_id, "trial-serving/handoff.json"
            )
            == first
        )


def test_unverified_probe_process_keeps_trial_fences_after_cleanup(tmp_path):
    from aptl.core.trial_ownership import trial_fence_owner
    from aptl.utils.probe_execution import run_bounded_probe_command
    from tests.test_readiness_probe_execution import Runner
    from tests.test_trial_serving import daemon_root

    runner = Runner(residual=("process-group-cleanup-unconfirmed",))
    with serving(tmp_path, readiness_options={"process_runner": runner}) as (
        handler,
        request,
        *_,
    ):

        def source(_scenario):
            return (
                run_bounded_probe_command(["approved-probe"], cwd=tmp_path, timeout=1)
                is not None
            )

        handler.readiness.owners = replace(handler.readiness.owners, services=source)
        with pytest.raises(
            ValueError, match="^trial-readiness-(?:probes-pending|blocked)$"
        ):
            finish(handler, request)
        assert runner.calls
        assert handler.readiness.has_pending_probes
        assert trial_fence_owner(handler.placement.backend.project_dir) is not None
        assert trial_fence_owner(daemon_root(handler)) is not None
        assert not (
            handler.cleanup.store.get_run_path(request.run_id)
            / "trial-serving/handoff.json"
        ).exists()


def test_later_passing_probes_cannot_clear_unconfirmed_cessation(tmp_path, admitted):
    from aptl.core.trial_ownership import claim_trial_owner
    from aptl.utils.probe_execution import run_bounded_probe_command
    from tests.test_readiness_probe_execution import Runner

    inputs, target, delivery, cleanup = admitted
    runner = Runner(residual=("process-group-cleanup-unconfirmed",))
    gate = readiness_for(
        inputs, target, cleanup.store, cleanup.clock, tmp_path, process_runner=runner
    )
    owner = b"a" * 64
    project, daemon = tmp_path / "owned-project", tmp_path / "owned-daemon"
    project.mkdir()
    daemon.mkdir()
    claim_trial_owner(project, owner)
    claim_trial_owner(daemon, owner)
    gate.bind_delivery(delivery.request, project, daemon, owner, "approved-daemon")

    def service(_scenario):
        result = run_bounded_probe_command(["approved-probe"], cwd=tmp_path, timeout=1)
        return result.returncode == 0

    gate.owners = replace(gate.owners, services=service)
    try:
        gate.record_clean(delivery.request, lambda: None)
        gate.prepare(delivery.request)
        with pytest.raises(ValueError, match="^trial-readiness-blocked$"):
            gate.check_live()
        runner.residual = ()
        with pytest.raises(ValueError, match="^trial-readiness-blocked$"):
            gate.check_live()
        assert not gate.execution_ready
        assert gate.has_pending_probes
        with pytest.raises(ValueError, match="^trial-readiness-blocked$"):
            target.participant_runtime.admit_action(
                sample_participant_action_admission_request(), RuntimeSnapshot()
            )
        with pytest.raises(ValueError, match="^trial-readiness-blocked$"):
            target.orchestrator.start(
                delivery.request.orchestration_plan, RuntimeSnapshot()
            )
    finally:
        gate.close()


def test_fully_ceased_preparation_refusal_releases_new_placement_fences(tmp_path):
    from aptl.core.lifecycle_guard import lifecycle_mutation_lock
    from aptl.core.trial_ownership import trial_fence_owner
    from tests.test_trial_serving import daemon_root

    with serving(tmp_path) as (handler, request, *_):
        original = handler.readiness.owners
        handler.readiness.owners = replace(original, containment=lambda: False)
        with pytest.raises(ValueError, match="^trial-readiness-blocked$"):
            handler.execute_trial(request)
        assert handler.runtime_unit.calls == 0
        assert trial_fence_owner(tmp_path) is None
        assert trial_fence_owner(daemon_root(handler)) is None
        with lifecycle_mutation_lock(tmp_path):
            pass
        handler.readiness.owners = original
        from aptl.core.deployment.backend_host_inventory import ProjectRuntimePresence

        backend = handler.placement.backend
        backend.presence = ProjectRuntimePresence(container_count=1, network_count=0)
        with pytest.raises(ValueError, match="^trial-placement-contaminated$"):
            handler.execute_trial(request)
        backend.presence = ProjectRuntimePresence(container_count=0, network_count=0)
        assert finish(handler, request).cleanup_receipt.trial_outcome == "succeeded"


def test_preparation_refusal_retains_ownership_from_a_prior_interruption(
    tmp_path, monkeypatch
):
    from aptl.core.trial_ownership import trial_fence_owner
    from tests.test_trial_serving import daemon_root

    with serving(tmp_path) as (handler, request, *_):
        prepare = handler.readiness.prepare

        def interrupted(_request):
            raise SystemExit("interrupted before dispatch")

        monkeypatch.setattr(handler.readiness, "prepare", interrupted)
        with pytest.raises(SystemExit):
            handler.execute_trial(request)
        project_owner = trial_fence_owner(tmp_path)
        daemon_owner = trial_fence_owner(daemon_root(handler))
        assert project_owner and daemon_owner
        monkeypatch.setattr(handler.readiness, "prepare", prepare)
        handler.readiness.owners = replace(
            handler.readiness.owners, containment=lambda: False
        )
        with pytest.raises(ValueError, match="^trial-readiness-blocked$"):
            handler.execute_trial(request)
        assert trial_fence_owner(tmp_path) == project_owner
        assert trial_fence_owner(daemon_root(handler)) == daemon_owner
        assert handler.runtime_unit.calls == 0
