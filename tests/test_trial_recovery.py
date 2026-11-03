"""Interrupted delivery preserves admission commitments before native effects."""

import json
from dataclasses import replace

import pytest
from raes_runtime.runtime_trial_unit import TrialPending

from aptl.core.trial_ownership import TRIAL_FENCE
from tests.test_trial_serving import serving
from tests.trial_recovery_fixture import assigned_serving, restarted_worker
from aptl.backends.trial_recovery import recover_interrupted_trial


def test_trial_intent_is_durable_before_runtime_effects(tmp_path):
    with serving(tmp_path, pending=True) as (handler, request, services, *_):
        observed = []

        def before_effects():
            intent = handler.cleanup.store.read_run_json(
                request.run_id, "trial-serving/intent.json"
            )
            assert intent is not None, "runtime dispatch preceded durable trial intent"
            assert intent["run_id"] == request.run_id
            assert intent["execution_attempt_id"] == request.execution_attempt_id
            assert intent["plan_entry_id"] == request.plan_entry_id
            assert intent["plan_digest"] == request.plan.plan_digest
            assert intent["instantiated_sdl_digest"] == request.instantiated_sdl_digest
            assert intent["native_attempt_id"] == handler.cleanup.native.binding.native_attempt_id
            assert services.events == []
            observed.append(intent)

        handler.runtime_unit.before_advance = before_effects
        with pytest.raises(TrialPending):
            handler.execute_trial(request)
        assert len(observed) == 1


@pytest.mark.parametrize(
    "corruption", ["missing", "malformed", "duplicate", "identity", "oversize"]
)
def test_corrupt_intent_blocks_redelivery_and_preserves_exclusion(tmp_path, corruption):
    with serving(tmp_path, pending=True) as (handler, request, *_):
        with pytest.raises(TrialPending):
            handler.execute_trial(request)
        path = handler.cleanup.store.get_run_path(request.run_id) / "trial-serving/intent.json"
        payload = json.loads(path.read_text())
        if corruption == "missing":
            path.unlink()
        elif corruption == "malformed":
            path.write_text("{")
        elif corruption == "duplicate":
            path.write_text('{"run_id":"another-run",' + path.read_text()[1:])
        elif corruption == "identity":
            payload["execution_attempt_id"] = "another-attempt"
            path.write_text(json.dumps(payload))
        else:
            path.write_text(" " * 16385)
        calls = handler.runtime_unit.calls
        with pytest.raises(ValueError, match="trial-intent-"):
            handler.execute_trial(request)
        assert handler.runtime_unit.calls == calls
        assert (tmp_path / TRIAL_FENCE).is_file()


@pytest.mark.parametrize("after_effects", [False, True])
def test_recovery_stops_only_the_assigned_attempt_and_seals_original_facts(tmp_path, after_effects):
    with assigned_serving(tmp_path) as case:
        request = case.binding.request
        if after_effects:
            with pytest.raises(TrialPending):
                case.handler.execute_trial(request)
        else:
            class InterruptedDelivery:
                def execute_trial(self, request):
                    raise RuntimeError("caller interrupted before dispatch")

            interrupted = replace(case.handler, runtime_unit=InterruptedDelivery())
            with pytest.raises(RuntimeError, match="caller interrupted"):
                interrupted.execute_trial(request)
        before = case.services.events.count("configure")
        store = case.handler.cleanup.store
        store.write_file(request.run_id, "evidence/partial.bin", b"partial capture bytes")
        control = case.cancellation()
        from aptl.backends.trial_recovery import recover_interrupted_trial

        result = recover_interrupted_trial(
            case.handler, case.binding, control,
            runtime=case.worker, clock=case.clock, identity="worker-437",
        )
        assert result.run.run_id == request.run_id
        assert result.run.run_status == "aborted"
        assert result.run.outcome_status == "not-evaluated"
        assert result.run.started_at == case.binding.assignment.started_at
        attempt = result.run.execution_accounting.attempts[-1]
        assert attempt.execution_attempt_id == request.execution_attempt_id
        assert attempt.execution_status == "cancelled"
        assert attempt.cleanup_status == "succeeded"
        assert result.manifest_path.parent.joinpath("evidence/partial.bin").read_bytes() == b"partial capture bytes"
        assert case.services.events.count("configure") == before
        assert result.resources_reusable
        assert not (tmp_path / TRIAL_FENCE).exists()
        assert case.records().accounting.started_runs == 1
        assert case.records().accounting.unstarted_runs == 7
        events = list(case.services.events)
        duplicate = recover_interrupted_trial(
            case.handler, case.binding, control,
            runtime=case.worker, clock=case.clock, identity="worker-437",
        )
        assert duplicate.idempotent
        assert duplicate.manifest_path == result.manifest_path
        assert duplicate.run == result.run
        assert case.services.events == events


def test_recovery_requires_coordinator_stop_intent_before_native_work(tmp_path):
    with assigned_serving(tmp_path) as case:
        control = case.coordinator.assigned_trial_control(
            case.experiment_id, case.binding.assignment_digest
        )
        from aptl.backends.trial_recovery import recover_interrupted_trial

        with pytest.raises(ValueError, match="trial-recovery-control-"):
            recover_interrupted_trial(
                case.handler, case.binding, control,
                runtime=case.worker, clock=case.clock, identity="worker-437",
            )
        assert case.services.events == []
        assert not (tmp_path / TRIAL_FENCE).exists()


def recover(case, control=None):
    return recover_interrupted_trial(
        case.handler, case.binding, control or case.cancellation(),
        runtime=case.worker, clock=case.clock, identity="worker-437",
    )


def test_failed_cleanup_seals_failure_and_keeps_both_fences(tmp_path):
    with assigned_serving(tmp_path, cleanup_fails=True) as case:
        with pytest.raises(TrialPending):
            case.handler.execute_trial(case.binding.request)
        control = case.cancellation()
        result = recover(case, control)
        attempt = result.run.execution_accounting.attempts[-1]
        assert attempt.execution_status == "cancelled"
        assert attempt.cleanup_status == "failed"
        assert not result.resources_reusable
        owned = case.handler.describe_trial(case.binding.request)
        assert (owned.project / TRIAL_FENCE).read_bytes() == owned.owner
        assert (owned.daemon_root / TRIAL_FENCE).read_bytes() == owned.owner
        events = list(case.services.events)
        duplicate = recover(case, control)
        assert duplicate.idempotent
        assert duplicate.manifest_path == result.manifest_path
        assert case.services.events == events


def test_unknown_cessation_preserves_partial_record_and_target_exclusion(tmp_path):
    with assigned_serving(tmp_path) as case:
        with pytest.raises(TrialPending):
            case.handler.execute_trial(case.binding.request)
        # The installed stop owner reports uncertainty; no terminal observation
        # or cleanup can be manufactured from the delivered cancellation alone.
        from raes_contracts.runtime_state import ApplyResult
        case.services.stop = lambda request, cause, snapshot: ApplyResult(False, snapshot)
        result = recover(case)
        assert result.run.record_state == "partial"
        assert result.run.ended_at is None
        assert not result.resources_reusable
        assert "cleanup" not in case.services.events
        assert (tmp_path / TRIAL_FENCE).is_file()


@pytest.mark.parametrize("corruption", ["missing", "malformed", "identity"])
def test_recovery_refuses_corrupt_intent_before_stop(tmp_path, corruption):
    with assigned_serving(tmp_path) as case:
        with pytest.raises(TrialPending):
            case.handler.execute_trial(case.binding.request)
        intent = case.handler.cleanup.store.get_run_path(case.binding.request.run_id) / "trial-serving/intent.json"
        if corruption == "missing":
            intent.unlink()
        elif corruption == "malformed":
            intent.write_text('{"run_id":"credential-canary-437"')
        else:
            payload = json.loads(intent.read_text())
            payload["execution_attempt_id"] = "credential-canary-437"
            intent.write_text(json.dumps(payload))
        with pytest.raises(ValueError, match="trial-") as error:
            recover(case)
        assert "credential-canary-437" not in str(error.value)
        assert not case.services.stopped
        assert (tmp_path / TRIAL_FENCE).is_file()


def test_recovery_owner_errors_expose_only_a_fixed_code_and_keep_exclusion(tmp_path):
    with assigned_serving(tmp_path) as case:
        with pytest.raises(TrialPending):
            case.handler.execute_trial(case.binding.request)
        class BrokenClock:
            def now(self):
                raise RuntimeError("credential-canary-437")
        with pytest.raises(ValueError, match="^trial-recovery-unavailable$") as error:
            recover_interrupted_trial(
                case.handler, case.binding, case.cancellation(), runtime=case.worker,
                clock=BrokenClock(), identity="worker-437",
            )
        assert error.value.__suppress_context__
        assert (tmp_path / TRIAL_FENCE).is_file()


def test_duplicate_recovery_never_removes_a_later_owners_fences(tmp_path):
    with assigned_serving(tmp_path) as case:
        with pytest.raises(TrialPending):
            case.handler.execute_trial(case.binding.request)
        control = case.cancellation()
        result = recover(case, control)
        from aptl.core.trial_ownership import claim_trial_owner
        owned = case.handler.describe_trial(case.binding.request)
        later = b"f" * 64
        claim_trial_owner(owned.project, later)
        claim_trial_owner(owned.daemon_root, later)
        events = list(case.services.events)
        replay = recover(case, control)
        assert replay.idempotent
        assert replay.manifest_path == result.manifest_path
        assert case.services.events == events
        assert (owned.project / TRIAL_FENCE).read_bytes() == later
        assert (owned.daemon_root / TRIAL_FENCE).read_bytes() == later


@pytest.mark.parametrize("boundary", ["receipt", "second-fence", "completion"])
def test_recovery_replays_crash_between_archive_and_fence_release(tmp_path, monkeypatch, boundary):
    import aptl.backends.trial_recovery as recovery
    with assigned_serving(tmp_path) as case:
        with pytest.raises(TrialPending):
            case.handler.execute_trial(case.binding.request)
        control = case.cancellation()
        owned = case.handler.describe_trial(case.binding.request)
        if boundary == "receipt":
            original = case.handler.cleanup.store.create_json_once
            def interrupted(*args, **kwargs):
                raise OSError("publication interrupted")
            monkeypatch.setattr(case.handler.cleanup.store, "create_json_once", interrupted)
        elif boundary == "second-fence":
            original = recovery.remove_contained_nofollow
            def interrupted(root, path):
                if root == owned.daemon_root:
                    raise OSError("release interrupted")
                return original(root, path)
            monkeypatch.setattr(recovery, "remove_contained_nofollow", interrupted)
        else:
            def interrupted(request):
                raise OSError("completion interrupted")
            monkeypatch.setattr(case.handler.readiness, "complete_delivery", interrupted)
        with pytest.raises(ValueError, match="trial-recovery-unavailable"):
            recover(case, control)
        if boundary != "completion":
            assert (owned.daemon_root / TRIAL_FENCE).is_file()
        events = list(case.services.events)
        monkeypatch.undo()
        result = recover(case, control)
        assert result.idempotent
        assert result.resources_reusable
        assert case.services.events == events
        assert not (owned.project / TRIAL_FENCE).exists()
        assert not (owned.daemon_root / TRIAL_FENCE).exists()
        # A verified replay must finish the readiness handoff as well, so a
        # subsequent externally supplied delivery can bind its fresh checks.
        owned.readiness.bind_delivery(
            replace(owned.request, execution_attempt_id="next-external-attempt"),
            owned.project, owned.daemon_root, b"f" * 64, owned.daemon,
        )


def test_concurrent_recovery_returns_the_same_archive_without_repeated_effects(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    with assigned_serving(tmp_path) as case:
        with pytest.raises(TrialPending):
            case.handler.execute_trial(case.binding.request)
        control = case.cancellation()
        start = Barrier(2)
        def recover_once():
            start.wait(timeout=10)
            try:
                return recover(case, control)
            except ValueError as error:
                assert str(error) in {"trial-recovery-busy", "trial-recovery-unavailable"}
                return None
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: recover_once(), range(2)))
        completed = [result for result in results if result is not None]
        assert completed
        replay = recover(case, control)
        assert replay.idempotent
        assert all(result.manifest_path == replay.manifest_path for result in completed)
        assert all(result.run == replay.run for result in completed)
        assert case.services.events.count("cleanup") == 1
        assert case.services.events.count("capture") == 1


def test_restart_uses_original_durable_ledgers_and_preserves_probe_uncertainty(tmp_path):
    with assigned_serving(tmp_path, durable=True) as original:
        request = original.binding.request
        with pytest.raises(TrialPending):
            original.handler.execute_trial(request)
        before = original.binding.outcome(identity="worker-437")
        effects = original.services.events.count("configure")
        control = original.cancellation()
        with restarted_worker(original, tmp_path) as case:
            restored = case.binding.outcome(identity="worker-437")
            assert restored.facts == before.facts
            assert restored.operations == before.operations
            assert restored.assignment_digest == before.assignment_digest
            result = recover(case, control)
            assert result.run.run_id == request.run_id
            assert result.run.started_at == original.binding.assignment.started_at
            assert result.run.execution_accounting.attempts[-1].execution_attempt_id == request.execution_attempt_id
            assert original.services.events.count("configure") == effects
            assert not result.resources_reusable
            assert (tmp_path / TRIAL_FENCE).is_file()
            assert case.records().accounting.unstarted_runs == 7


def test_incomplete_capture_remains_distinct_from_execution_and_cleanup(tmp_path):
    from raes_contracts.runtime_state import ApplyResult
    from raes_runtime.runtime_trial_services import TrialCaptureObservation
    with assigned_serving(tmp_path) as case:
        with pytest.raises(TrialPending):
            case.handler.execute_trial(case.binding.request)
        def failed_capture(request, snapshot):
            case.services.events.append("capture")
            return ApplyResult(False, snapshot), TrialCaptureObservation(
                complete=False, evidence=(case.services.evidence(request, "capture"),),
            )
        case.services.capture = failed_capture
        result = recover(case)
        attempt = result.run.execution_accounting.attempts[-1]
        assert attempt.execution_status == "cancelled"
        assert attempt.capture_status == "partial"
        assert attempt.cleanup_status == "unobserved"
        assert not result.resources_reusable
        assert (tmp_path / TRIAL_FENCE).is_file()
        assert result.run.outcome_status == "not-evaluated"
        assert result.manifest_path.is_file()


def test_archive_verification_failure_keeps_native_exclusion(tmp_path, monkeypatch):
    import aptl.backends.trial_recovery as recovery
    with assigned_serving(tmp_path) as case:
        with pytest.raises(TrialPending):
            case.handler.execute_trial(case.binding.request)
        monkeypatch.setattr(recovery, "verify_sealed_archive", lambda *args: None)
        with pytest.raises(ValueError, match="trial-recovery-unavailable"):
            recover(case)
        owned = case.handler.describe_trial(case.binding.request)
        assert (owned.project / TRIAL_FENCE).read_bytes() == owned.owner
        assert (owned.daemon_root / TRIAL_FENCE).read_bytes() == owned.owner


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_recovery_finishes_the_installed_participant_only_after_reusable_cleanup(tmp_path, cleanup_fails):
    from unittest.mock import Mock
    with assigned_serving(tmp_path, cleanup_fails=cleanup_fails) as original:
        application = Mock()
        case = replace(original, handler=replace(original.handler, participants=application))
        with pytest.raises(TrialPending):
            case.handler.execute_trial(case.binding.request)
        configurations = application.configure.call_count
        control = case.cancellation()
        result = recover(case, control)
        application.admit.assert_called_with(case.binding.request)
        assert application.configure.call_count == configurations
        if cleanup_fails:
            application.finish.assert_not_called()
        else:
            application.finish.assert_called_once_with(case.binding.request)
            replay = recover(case, control)
            assert replay.idempotent
            application.finish.assert_called_once()
        assert result.resources_reusable is not cleanup_fails


@pytest.mark.parametrize("foreign", [None, "project", "daemon"])
def test_recovery_after_intent_before_fences_seals_and_retains_exclusion(tmp_path, monkeypatch, foreign):
    import aptl.backends.trial_serving as serving_module
    with assigned_serving(tmp_path) as case:
        retain = serving_module.retain_trial_intent
        def interrupted(store, intent):
            retain(store, intent)
            raise RuntimeError("interrupted after durable intent")
        monkeypatch.setattr(serving_module, "retain_trial_intent", interrupted)
        with pytest.raises(RuntimeError, match="interrupted after durable intent"):
            case.handler.execute_trial(case.binding.request)
        owned = case.handler.describe_trial(case.binding.request)
        assert not (owned.project / TRIAL_FENCE).exists()
        assert not (owned.daemon_root / TRIAL_FENCE).exists()
        assert case.services.events == []
        store = case.handler.cleanup.store
        store.write_file(owned.request.run_id, "evidence/retained.partial", b"retained before handoff")
        control = case.cancellation()
        if foreign is not None:
            from aptl.core.trial_ownership import claim_trial_owner
            root = owned.project if foreign == "project" else owned.daemon_root
            other = owned.daemon_root if foreign == "project" else owned.project
            # The placement child may not yet exist at this crash boundary.
            root.mkdir(parents=True, exist_ok=True)
            claim_trial_owner(root, b"f" * 64)
            with pytest.raises(ValueError, match="trial-recovery-"):
                recover(case, control)
            assert (root / TRIAL_FENCE).read_bytes() == b"f" * 64
            assert not (other / TRIAL_FENCE).exists()
            assert case.services.events == []
            return
        result = recover(case, control)
        assert result.run.run_id == owned.request.run_id
        assert result.manifest_path.parent.joinpath("evidence/retained.partial").read_bytes() == b"retained before handoff"
        assert "configure" not in case.services.events
        assert not result.resources_reusable
        marker = json.loads(result.manifest_path.with_name("seal.json").read_text())
        assert any(item["code"] == "probe-cessation-unverified" for item in marker["completeness"]["limitations"])
        assert (owned.project / TRIAL_FENCE).read_bytes() == owned.owner
        assert (owned.daemon_root / TRIAL_FENCE).read_bytes() == owned.owner
        events = list(case.services.events)
        duplicate = recover(case, control)
        assert duplicate.idempotent
        assert duplicate.manifest_path == result.manifest_path
        assert not duplicate.resources_reusable
        assert case.services.events == events


def test_old_recovery_replay_preserves_a_later_completed_readiness_delivery(tmp_path):
    with assigned_serving(tmp_path) as case:
        with pytest.raises(TrialPending):
            case.handler.execute_trial(case.binding.request)
        control = case.cancellation()
        first = recover(case, control)
        owned = case.handler.describe_trial(case.binding.request)
        readiness = owned.readiness
        later = replace(owned.request, execution_attempt_id="later-external-attempt")
        readiness.bind_delivery(later, owned.project, owned.daemon_root, b"b" * 64, owned.daemon)
        readiness.record_clean(later, lambda: None)
        readiness.complete_delivery(later)
        references = readiness.references
        assert references
        replay = recover(case, control)
        assert replay.idempotent
        assert replay.manifest_path == first.manifest_path
        assert readiness.references == references
        readiness.bind_delivery(
            replace(owned.request, execution_attempt_id="third-external-attempt"),
            owned.project, owned.daemon_root, b"c" * 64, owned.daemon,
        )
