"""Trial isolation wraps the released RAES scheduler and native cleanup owner."""

from contextlib import contextmanager
from dataclasses import replace
import hashlib
import threading
from types import SimpleNamespace

import pytest
from raes_runtime import RuntimeControlPlane
from raes_runtime.runtime_trial_unit import TrialPending

from aptl.backends.trial_serving import DockerTrialPlacement, LilraeTrialUnit
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

    def __init__(self, runtime, experiment_id):
        self.runtime, self.experiment_id = runtime, experiment_id
        experiment = runtime._experiments[experiment_id]
        records = runtime._store.load_runtime_decisions()
        slot = experiment._slots(records)[0]
        attempt = experiment._attempt(slot, 1, records)
        self.unit = experiment._unit(slot, attempt, None)
        self.request = self.unit.request
        self.calls = 0
        self.before_advance = lambda: None

    def execute_trial(self, request):
        assert request == self.request
        self.calls += 1
        self.before_advance()
        results = self.runtime.experiment_results(self.experiment_id)
        if not results:
            self.runtime.advance_experiment(self.experiment_id)
            results = self.runtime.experiment_results(self.experiment_id)
        if not results:
            raise TrialPending("reconcile through RAES")
        return results[0]


@contextmanager
def serving(tmp_path, *, failed=False, pending=False, cleanup_fails=False):
    inputs, manifest = runtime_inputs(tmp_path)
    services = Services(
        tmp_path, failed=failed, pending=pending, cleanup_fails=cleanup_fails
    )
    state_root = tmp_path / "placement-state"
    state_root.mkdir()
    backend = PlacementBackend(tmp_path)
    placement = DockerTrialPlacement(backend, state_root)
    with RuntimeControlPlane(target_for(manifest)) as runtime:
        experiment_id = runtime.admit_experiment(inputs, services=services)
        delivery = SchedulerDelivery(runtime, experiment_id)
        request = delivery.request
        cleanup = services.cleanups[request.execution_attempt_id]
        handler = LilraeTrialUnit(
            delivery, cleanup, placement, delivery.unit.run._target_scope
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


def test_trial_serving_refuses_unsupported_platform_before_effects(tmp_path, monkeypatch):
    with serving(tmp_path) as (handler, request, *_):
        monkeypatch.setattr("aptl.backends.trial_serving.os", SimpleNamespace(name="nt"))
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
