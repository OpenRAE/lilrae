"""Trial isolation wraps the released RAES scheduler and native cleanup owner."""

from contextlib import contextmanager
from dataclasses import replace
import hashlib
import threading
from types import SimpleNamespace

import pytest
from raes_runtime import RuntimeControlPlane
from raes_runtime.runtime_trial_unit import TrialPending

from aptl.backends.trial_serving import (
    DockerTrialPlacement,
    LilraeTrialUnit,
    report_trial_outcomes,
    TrialOutcomeReporting,
)
from aptl.core.deployment.backend_host_inventory import ProjectRuntimePresence
from aptl.core.lifecycle_guard import lifecycle_mutation_lock
from aptl.core.lifecycle_policy import LifecycleBusyError
from aptl.core.trial_ownership import TRIAL_FENCE
from tests.cleanup_runtime_fixture import Services, runtime_inputs, target_for


class PlacementBackend:
    """Checked daemon/project observations without a live Docker dependency."""

    def __init__(self, root):
        self.project_dir = root
        self.identity = "approved-daemon"
        self.presence = ProjectRuntimePresence()
        self.volumes = ()
        self.ownership = None

    def daemon_identity(self):
        return self.identity

    def observe_project_runtime(self):
        return self.presence

    def _scoped_compose_volume_names(self):
        return self.volumes

    def _load_resource_ownership(self):
        return self.ownership


class SchedulerDelivery:
    """Test transport: deliver progress to RAES's public external scheduler.

    RAES owns the attempt and request; no local trial order or identity exists.
    The test reads that already-admitted request to exercise BackendTrialUnit.
    """

    def __init__(self, runtime, experiment_id, entry_index=0):
        self.runtime, self.experiment_id = runtime, experiment_id
        experiment = runtime._experiments[experiment_id]
        records = runtime._store.load_runtime_decisions()
        slot = experiment._slots(records)[entry_index]
        attempt = experiment._attempt(slot, 1, records)
        self.unit = experiment._unit(slot, attempt, None)
        self.request = self.unit.request
        self.calls = 0
        self.before_advance = lambda: None

    def execute_trial(self, request):
        assert request == self.request
        self.calls += 1
        self.before_advance()
        for _ in range(2):
            for result in self.runtime.experiment_results(self.experiment_id):
                if result.cleanup_receipt.run_id == request.run_id:
                    return result
            self.runtime.advance_experiment(self.experiment_id)
        raise TrialPending("reconcile through RAES")


@contextmanager
def serving(
    tmp_path,
    *,
    failed=False,
    pending=False,
    cleanup_fails=False,
    entry_index=0,
    on_timeout=None,
    content_reporting=False,
    native_policy=None,
    native_refusal=False,
):
    installed = ()
    if native_policy:
        from tests.trial_reporting_fixture import native_failure_bindings

        installed = native_failure_bindings()
    inputs, manifest = runtime_inputs(
        tmp_path,
        on_timeout=on_timeout,
        content_reporting=content_reporting,
        native_policy=native_policy,
        native_bindings=installed,
    )
    services = Services(
        tmp_path, failed=failed, pending=pending, cleanup_fails=cleanup_fails
    )
    state_root = tmp_path / "placement-state"
    state_root.mkdir()
    backend = PlacementBackend(tmp_path)
    placement = DockerTrialPlacement(backend, state_root)
    target = target_for(manifest, native_bindings=installed)
    if native_refusal:
        target.participant_runtime.autonomous_execution.cancel(
            "participant.behavior.red"
        )
    with RuntimeControlPlane(target) as runtime:
        experiment_id = runtime.admit_experiment(inputs, services=services)
        delivery = SchedulerDelivery(runtime, experiment_id, entry_index)
        request = delivery.request
        cleanup = services.cleanups[request.execution_attempt_id]
        handler = LilraeTrialUnit(
            delivery,
            cleanup,
            placement,
            delivery.unit.run._target_scope,
            TrialOutcomeReporting(runtime, experiment_id, lambda request, result: {}),
        )
        yield handler, request, services, runtime, experiment_id


def finish(handler, request):
    for _ in range(40):
        try:
            return handler.execute_trial(request)
        except TrialPending:
            continue
    pytest.fail("RAES did not reach a terminal result")


@pytest.mark.parametrize("outcome", ["succeeded", "failed", "cancelled", "timed-out"])
def test_real_runtime_preserves_outcome_partial_evidence_and_cleanup(tmp_path, outcome):
    with serving(
        tmp_path,
        failed=outcome == "failed",
        pending=outcome in {"cancelled", "timed-out"},
    ) as (handler, request, services, runtime, experiment_id):
        if outcome in {"cancelled", "timed-out"}:
            with pytest.raises(TrialPending):
                handler.execute_trial(request)
            if outcome == "cancelled":
                runtime.cancel_experiment(experiment_id)
            else:
                # Expire the runtime's retained attempt allowance without a
                # real-time wait or a LilRAE-owned timeout controller.
                handler.runtime_unit.unit._deadline = 0
        result = finish(handler, request)
        assert result.cleanup_receipt.trial_outcome == outcome
        assert result.cleanup_receipt.cleanup_status == "succeeded"
        assert result.evidence
        assert result.cleanup_evidence
        assert services.events[:3] == ["configure", "capture", "cleanup"]
        assert not (tmp_path / TRIAL_FENCE).exists()
        assert not (daemon_root(handler) / TRIAL_FENCE).exists()
        with lifecycle_mutation_lock(tmp_path):
            pass


def daemon_root(handler):
    return handler.placement.state_root / hashlib.sha256(b"approved-daemon").hexdigest()


@pytest.mark.parametrize("contamination", ["container", "network", "volume", "unknown"])
def test_contamination_prevents_dispatch_and_has_no_fence(tmp_path, contamination):
    with serving(tmp_path) as (handler, request, *_):
        backend = handler.placement.backend
        backend.presence = ProjectRuntimePresence(
            container_count=int(contamination == "container"),
            network_count=int(contamination == "network"),
            error="unavailable" if contamination == "unknown" else "",
        )
        backend.volumes = ("residual",) if contamination == "volume" else ()
        with pytest.raises(ValueError, match="trial-placement-contaminated"):
            handler.execute_trial(request)
        assert handler.runtime_unit.calls == 0
        assert not (tmp_path / TRIAL_FENCE).exists()


def test_native_receipt_contamination_is_not_mistaken_for_empty_compose(
    tmp_path, monkeypatch
):
    with serving(tmp_path) as (handler, request, *_):
        handler.placement.backend.ownership = SimpleNamespace(
            receipts=lambda kind: (object(),)
        )
        monkeypatch.setattr(
            "aptl.backends.trial_serving.confirm_native_absence", lambda *args: False
        )
        with pytest.raises(ValueError, match="trial-placement-contaminated"):
            handler.execute_trial(request)
        assert handler.runtime_unit.calls == 0


@pytest.mark.parametrize("limit", ["operations", "timeout"])
def test_installed_limits_are_checked_before_effects(tmp_path, limit):
    with serving(tmp_path) as (handler, request, *_):
        if limit == "operations":
            handler = replace(handler, max_operations=1)
        else:
            handler = replace(handler, max_attempt_seconds=1)
        with pytest.raises(ValueError, match="trial-serving-resource-limit"):
            handler.execute_trial(request)
        assert handler.runtime_unit.calls == 0
        assert not (tmp_path / TRIAL_FENCE).exists()


def test_trial_serving_refuses_unsupported_platform_before_effects(
    tmp_path, monkeypatch
):
    with serving(tmp_path) as (handler, request, *_):
        monkeypatch.setattr(
            "aptl.backends.trial_serving.os", SimpleNamespace(name="nt")
        )
        with pytest.raises(ValueError, match="trial-serving-posix-required"):
            handler.execute_trial(request)
        assert handler.runtime_unit.calls == 0
        assert not (tmp_path / TRIAL_FENCE).exists()


def test_pending_work_excludes_unrelated_lifecycle_and_other_projects(tmp_path):
    with serving(tmp_path, pending=True) as (handler, request, *_):
        with pytest.raises(TrialPending):
            handler.execute_trial(request)
        with pytest.raises(LifecycleBusyError):
            with lifecycle_mutation_lock(tmp_path):
                pass
        other = tmp_path / "other-project"
        other.mkdir()
        # An independently composed worker uses the same daemon state root.
        with serving(other) as (second, other_request, *_):
            placement = replace(
                second.placement, state_root=handler.placement.state_root
            )
            second = replace(second, placement=placement)
            with pytest.raises(LifecycleBusyError):
                second.execute_trial(other_request)
            assert second.runtime_unit.calls == 0


def test_cleanup_failure_retains_evidence_and_fences_on_reentry(tmp_path):
    with serving(tmp_path, cleanup_fails=True) as (handler, request, services, *_):
        result = finish(handler, request)
        assert result.cleanup_receipt.cleanup_status == "failed"
        assert result.cleanup_evidence
        assert (tmp_path / TRIAL_FENCE).exists()
        assert (daemon_root(handler) / TRIAL_FENCE).exists()
        assert (
            finish(replace(handler), request).cleanup_receipt == result.cleanup_receipt
        )
        assert services.events.count("configure") == 1
        with pytest.raises(LifecycleBusyError):
            with lifecycle_mutation_lock(tmp_path):
                pass


def test_worker_callback_shares_lock_and_unrelated_thread_is_excluded(tmp_path):
    import anyio

    with serving(tmp_path) as (handler, request, *_):
        outcomes = []

        def unrelated():
            try:
                with lifecycle_mutation_lock(tmp_path):
                    outcomes.append("unsafe")
            except LifecycleBusyError:
                outcomes.append("excluded")

        def related():
            with lifecycle_mutation_lock(tmp_path):
                outcomes.append("related")

        async def worker():
            await anyio.to_thread.run_sync(related)

        def check():
            thread = threading.Thread(target=unrelated)
            thread.start()
            thread.join(timeout=5)
            assert not thread.is_alive()
            anyio.run(worker)

        handler.runtime_unit.before_advance = check
        with pytest.raises(TrialPending):
            handler.execute_trial(request)
        assert outcomes == ["excluded", "related"]


def test_unverified_cleanup_never_releases_fences(tmp_path, monkeypatch):
    with serving(tmp_path) as (handler, request, *_):
        finish(handler, request)

        def reject(observation):
            raise ValueError("unverified-cleanup")

        monkeypatch.setattr(handler.cleanup, "verify_observation", reject)
        with pytest.raises(ValueError, match="unverified-cleanup"):
            finish(handler, request)
        assert (tmp_path / TRIAL_FENCE).exists()
        assert (daemon_root(handler) / TRIAL_FENCE).exists()


def test_native_cleanup_worker_can_enter_project_lock(tmp_path, monkeypatch):
    with serving(tmp_path) as (handler, request, *_):
        native = handler.cleanup.native
        execute = native.execute
        observed = []

        def cleanup_with_lock(action, timeout):
            with lifecycle_mutation_lock(tmp_path):
                observed.append(action)
                return execute(action, timeout)

        monkeypatch.setattr(native, "execute", cleanup_with_lock)
        assert finish(handler, request).cleanup_receipt.cleanup_status == "succeeded"
        assert "destroy" in observed


def test_daemon_change_after_delivery_retains_fences(tmp_path):
    with serving(tmp_path) as (handler, request, *_):
        finish(handler, request)
        handler.runtime_unit.before_advance = lambda: setattr(
            handler.placement.backend, "identity", "another-daemon"
        )
        with pytest.raises(ValueError, match="trial-daemon-changed"):
            handler.execute_trial(request)
        assert (tmp_path / TRIAL_FENCE).exists()
        assert (daemon_root(handler) / TRIAL_FENCE).exists()


def test_independent_daemon_has_an_independent_dispatch_slot(tmp_path):
    with serving(tmp_path, pending=True) as (handler, request, *_):
        with pytest.raises(TrialPending):
            handler.execute_trial(request)
        other = tmp_path / "other-project"
        other.mkdir()
        with serving(other) as (second, other_request, *_):
            placement = replace(
                second.placement, state_root=handler.placement.state_root
            )
            second = replace(second, placement=placement)
            second.placement.backend.identity = "independent-daemon"
            assert (
                finish(second, other_request).cleanup_receipt.cleanup_status
                == "succeeded"
            )


def test_daemon_state_symlink_is_refused_before_dispatch(tmp_path):
    with serving(tmp_path) as (handler, request, *_):
        outside = tmp_path / "outside"
        outside.mkdir()
        daemon_root(handler).symlink_to(outside, target_is_directory=True)
        with pytest.raises(ValueError):
            handler.execute_trial(request)
        assert handler.runtime_unit.calls == 0
        assert list(outside.iterdir()) == []


def test_handoff_preserves_admitted_identity_and_partial_evidence(tmp_path):
    import json

    with serving(tmp_path, failed=True) as (handler, request, *_):
        result = finish(handler, request)
        receipt = json.loads(
            (
                tmp_path / "runs" / request.run_id / "trial-serving/handoff.json"
            ).read_text()
        )
        entry = request.plan.entries[request.plan_entry_id]
        assert receipt["run_id"] == request.run_id
        assert receipt["plan_digest"] == request.plan.plan_digest
        assert receipt["entry_digest"] == entry.entry_digest
        assert receipt["instantiated_sdl_digest"] == request.instantiated_sdl_digest
        assert receipt["execution_attempt_id"] == request.execution_attempt_id
        assert receipt["evidence_record_refs"] == [
            r.evidence_record_id for r in result.evidence
        ]
        assert receipt["cleanup_evidence_record_refs"] == [
            r.evidence_record_id for r in result.cleanup_evidence
        ]
        assert finish(handler, request) == result


@pytest.mark.parametrize(
    "case", ["success", "failure", "partial-capture", "cleanup-failure", "invalidation"]
)
def test_factorial_reporting_uses_shared_producer(tmp_path, case):
    from raes_contracts.contracts import ExperimentInvalidationModel
    from raes_runtime.experiment_records import ExperimentRunMetadata

    with serving(
        tmp_path, failed=case == "failure", cleanup_fails=case == "cleanup-failure"
    ) as (handler, _, services, runtime, experiment_id):
        if case == "partial-capture":
            capture = services.capture

            def partial_capture(request, snapshot):
                applied, observation = capture(request, snapshot)
                return applied, observation.model_copy(update={"complete": False})

            services.capture = partial_capture
        seen = set()
        plan = handler.runtime_unit.request.plan
        assert len(plan.entries) == 8
        for index in range(len(plan.entries)):
            delivery = SchedulerDelivery(runtime, experiment_id, index)
            request = delivery.request
            unit = replace(
                handler,
                runtime_unit=delivery,
                cleanup=services.cleanups[request.execution_attempt_id],
            )
            # A failed cleanup correctly fences this placement. Each condition
            # gets a separately approved placement for this reporting check.
            if case == "cleanup-failure" and index:
                break
            result = finish(unit, request)
            seen.add(request.run_id)
            assert result.cleanup_receipt.run_id == request.run_id
            assert result.evidence
            assert result.cleanup_evidence
        metadata = {}
        if case == "invalidation":
            metadata = {
                run_id: ExperimentRunMetadata(
                    outcome_status="inconclusive",
                    invalidation=ExperimentInvalidationModel(
                        invalidated_at="2026-11-02T12:00:00Z",
                        reason="required evidence lost",
                    ),
                )
                for run_id in seen
            }
        bundle = report_trial_outcomes(runtime, experiment_id, metadata=metadata)
        runs = {run.run_id: run for run in bundle.runs}
        assert seen <= runs.keys()
        for run_id in seen:
            run = runs[run_id]
            accounting = run.execution_accounting
            assert accounting.plan_id == plan.plan_id
            assert accounting.plan_digest == plan.plan_digest
            assert (
                accounting.entry_digest
                == plan.entries[accounting.plan_entry_id].entry_digest
            )
            assert (
                accounting.participant_configurations
                == plan.entries[accounting.plan_entry_id].participant_configurations
            )
            attempt = accounting.attempts[-1]
            assert attempt.execution_status == (
                "failed" if case == "failure" else "succeeded"
            )
            assert attempt.capture_status == (
                "partial" if case == "partial-capture" else "complete"
            )
            assert attempt.cleanup_status == (
                "failed" if case == "cleanup-failure" else "succeeded"
            )
            assert attempt.configuration_status == "observed"
            assert attempt.evidence_record_refs
            assert run.run_status == (
                "invalidated"
                if case == "invalidation"
                else "failed"
                if case == "failure"
                else "completed"
            )
            assert run.outcome_status == (
                "inconclusive" if case == "invalidation" else "not-evaluated"
            )
            assert run.record_state == "partial"
        assert len(seen) == (1 if case == "cleanup-failure" else 8)


def test_conflicting_handoff_retains_fences_and_owner_evidence(tmp_path):
    with serving(tmp_path) as (handler, request, services, *_):
        handler.cleanup.store.create_run_json_once(
            request.run_id, "trial-serving/handoff.json", {"run_id": "wrong"}
        )
        with pytest.raises(ValueError, match="already exists"):
            finish(handler, request)
        assert services.records
        assert (tmp_path / TRIAL_FENCE).exists()
        assert (daemon_root(handler) / TRIAL_FENCE).exists()


@pytest.mark.parametrize("entry_index", range(8))
def test_cleanup_failure_per_factorial_entry(tmp_path, entry_index):
    with serving(tmp_path, cleanup_fails=True, entry_index=entry_index) as (
        handler,
        request,
        _,
        runtime,
        experiment_id,
    ):
        # Exercise this admitted unit on its own isolated placement. The shared
        # ledger still owns its execution and record production.
        handler = replace(handler, runtime_unit=handler.runtime_unit.unit)
        result = finish(handler, request)
        assert result.cleanup_receipt.cleanup_status == "failed"
        assert result.cleanup_evidence
        bundle = report_trial_outcomes(runtime, experiment_id, metadata={})
        (run,) = bundle.runs
        assert run.run_id == request.run_id
        assert run.execution_accounting.plan_entry_id == request.plan_entry_id
        assert run.execution_accounting.attempts[-1].cleanup_status == "failed"
        assert run.outcome_status != "succeeded"
        assert (tmp_path / TRIAL_FENCE).exists()


@pytest.mark.parametrize("entry_index", range(8))
@pytest.mark.parametrize(
    "case",
    [
        "rejected",
        "withheld",
        "partial_success",
        "unknown",
        "timeout-fail",
        "timeout-abort",
        "missing-evidence",
    ],
)
def test_failure_reporting_per_factorial_entry(tmp_path, entry_index, case):
    from raes_contracts.contracts import (
        ParticipantActionResultModel,
        ParticipantBehaviorHistoryEventModel,
    )
    from raes_runtime.experiment_records import ExperimentRunMetadata

    timeout = case.startswith("timeout")
    with serving(
        tmp_path,
        entry_index=entry_index,
        pending=timeout,
        failed=case in {"rejected", "withheld"},
        on_timeout="abort" if case == "timeout-abort" else "cleanup-and-fail",
    ) as (handler, request, services, runtime, experiment_id):
        delivery = handler.runtime_unit
        unit = delivery.unit
        handler = replace(handler, runtime_unit=unit)
        action_status = (
            case
            if case in {"rejected", "withheld", "partial_success", "unknown"}
            else None
        )
        if action_status:
            configure = services.configure

            def configured(request, snapshot):
                applied, observation = configure(request, snapshot)
                action = ParticipantActionResultModel(
                    status=action_status,
                    participant_address="agents.operator",
                    episode_id="episode",
                    action_instance_id="action-1",
                    action_contract_address="actions.perform",
                    observation_point="result-1",
                )
                event = ParticipantBehaviorHistoryEventModel(
                    event_type="observation_emitted",
                    timestamp="2026-11-02T12:00:00Z",
                    participant_address="agents.operator",
                    episode_id="episode",
                    action_instance_id="action-1",
                    action_contract_address="actions.perform",
                    action_result=action,
                )
                observed = replace(
                    applied.snapshot,
                    participant_behavior_history={
                        "agents.operator": [event.model_dump(mode="json")]
                    },
                )
                return replace(applied, snapshot=observed), observation

            services.configure = configured
        if case == "missing-evidence":
            capture = services.capture

            def missing_capture(request, snapshot):
                applied, observation = capture(request, snapshot)
                return applied, observation.model_copy(
                    update={"complete": False, "evidence": ()}
                )

            services.capture = missing_capture
        observed_metadata = {}

        def evaluate(request, result):
            if result is None:
                return observed_metadata
            # Task-evaluator test double reads retained owner facts. Production
            # reporting must invoke it, and must preserve its scientific verdict.
            history = result.execution_snapshot.participant_behavior_history
            verdict = "not-evaluated"
            if history:
                observed_status = history["agents.operator"][0]["action_result"][
                    "status"
                ]
                verdict = {
                    "rejected": "failed",
                    "withheld": "inconclusive",
                    "partial_success": "partial",
                    "unknown": "inconclusive",
                }[observed_status]
            observed_metadata[request.run_id] = ExperimentRunMetadata(
                outcome_status=verdict
            )
            return observed_metadata

        handler = replace(
            handler, reporting=replace(handler.reporting, metadata=evaluate)
        )
        if timeout:
            with pytest.raises(TrialPending):
                handler.execute_trial(request)
            unit._deadline = 0
        result = finish(handler, request)
        assert request.run_id in observed_metadata
        scientific = {
            "rejected": "failed",
            "withheld": "inconclusive",
            "partial_success": "partial",
            "unknown": "inconclusive",
        }.get(case, "not-evaluated")
        bundle = report_trial_outcomes(
            runtime,
            experiment_id,
            metadata=observed_metadata,
        )
        (run,) = bundle.runs
        attempt = run.execution_accounting.attempts[-1]
        assert run.run_id == request.run_id
        assert run.execution_accounting.plan_entry_id == request.plan_entry_id
        expected_execution = (
            "aborted"
            if case == "timeout-abort"
            else "timed-out"
            if timeout
            else "failed"
            if case in {"rejected", "withheld"}
            else "succeeded"
        )
        assert attempt.execution_status == expected_execution
        assert run.run_status == (
            "aborted"
            if case == "timeout-abort"
            else "failed"
            if expected_execution in {"failed", "timed-out"}
            else "completed"
        )
        assert run.outcome_status == scientific
        assert attempt.capture_status == (
            "partial" if case == "missing-evidence" else "complete"
        )
        assert attempt.cleanup_status == "succeeded"
        assert result.evidence
        assert result.cleanup_evidence
        assert attempt.evidence_record_refs
        if action_status:
            history = result.execution_snapshot.participant_behavior_history
            assert (
                history["agents.operator"][0]["action_result"]["status"]
                == action_status
            )
            source = bundle.sources[0]
            retained = source.execution_snapshots[request.execution_attempt_id]
            assert retained.participant_behavior_history == history
        if case == "missing-evidence":
            assert request.run_id not in bundle.eligible_run_ids
            assert bundle.validation_by_run[request.run_id] == "failed"


def test_trial_reporting_failure_retains_fences(tmp_path):
    with serving(tmp_path) as (handler, request, *_):
        handler = replace(
            handler, reporting=replace(handler.reporting, experiment_id="unknown")
        )
        from raes_contracts.errors import NotFoundError

        with pytest.raises(NotFoundError):
            finish(handler, request)
        assert (tmp_path / TRIAL_FENCE).exists()
        assert (daemon_root(handler) / TRIAL_FENCE).exists()


@pytest.mark.parametrize("entry_index", range(8))
def test_content_backed_reporting_requires_declared_evidence(tmp_path, entry_index):
    from tests.trial_reporting_fixture import ReportingEvidence

    with serving(tmp_path, entry_index=entry_index, content_reporting=True) as (
        handler,
        request,
        services,
        runtime,
        experiment_id,
    ):
        evidence = ReportingEvidence(
            runtime._experiments[experiment_id].inputs, services
        )
        services.capture = evidence.capture
        handler = replace(
            handler,
            runtime_unit=handler.runtime_unit.unit,
            reporting=replace(
                handler.reporting,
                metadata=evidence.evaluate,
                evidence_reader=evidence.reader,
            ),
        )
        result = finish(handler, request)
        baseline = report_trial_outcomes(
            runtime,
            experiment_id,
            metadata=evidence.metadata,
            evidence_reader=evidence.reader,
        )
        assert baseline.validation_by_run[request.run_id] == "passed", (
            baseline.validation_failures
        )
        assert baseline.runs[0].outcome_status == "succeeded"
        assert request.run_id in baseline.eligible_run_ids
        assert result.evidence
        evidence.omit_required = True
        missing = report_trial_outcomes(
            runtime,
            experiment_id,
            metadata=evidence.metadata,
            evidence_reader=evidence.reader,
        )
        assert missing.validation_by_run[request.run_id] == "failed"
        assert request.run_id not in missing.eligible_run_ids
        assert missing.sources[0].execution_snapshots


def test_pending_delivery_publishes_partial_records_without_a_terminal_verdict(
    tmp_path,
):
    from tests.trial_reporting_fixture import RecordingArchive

    with serving(tmp_path, pending=True) as (handler, request, services, *_):
        archive = RecordingArchive()
        observed_results = []

        def metadata(request, result):
            observed_results.append(result)
            return {}

        handler = replace(
            handler,
            reporting=replace(handler.reporting, metadata=metadata, archive=archive),
        )
        with pytest.raises(TrialPending):
            handler.execute_trial(request)
        assert observed_results == [None]
        (run,) = archive.runs.values()
        assert run.run_id == request.run_id
        assert run.run_status == "indeterminate"
        assert run.outcome_status == "not-evaluated"
        assert run.ended_at is None
        attempt = run.execution_accounting.attempts[-1]
        assert attempt.execution_attempt_id == request.execution_attempt_id
        assert attempt.configuration_status == "observed"
        assert attempt.evidence_record_refs
        assert attempt.cleanup_receipt is None
        assert attempt.cleanup_status == "unobserved"
        assert request.run_id in archive.sources
        assert (tmp_path / TRIAL_FENCE).exists()
        assert (daemon_root(handler) / TRIAL_FENCE).exists()
        assert services.events == ["configure"]


def test_failed_partial_publication_retains_fences_and_does_not_claim_completion(
    tmp_path,
):
    from tests.trial_reporting_fixture import RecordingArchive

    class UnavailableArchive(RecordingArchive):
        def write_sources(self, source):
            raise OSError("private archive detail")

    with serving(tmp_path, pending=True) as (handler, request, services, *_):
        handler = replace(
            handler, reporting=replace(handler.reporting, archive=UnavailableArchive())
        )
        with pytest.raises(ValueError, match="^trial-serving-owner-unavailable$"):
            handler.execute_trial(request)
        assert (tmp_path / TRIAL_FENCE).exists()
        assert (daemon_root(handler) / TRIAL_FENCE).exists()
        assert services.events == ["configure"]
        assert services.records
