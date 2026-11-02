"""Real shared-runtime progression invokes native cleanup after capture."""

import pytest
from raes_runtime import RuntimeControlPlane

from tests.cleanup_runtime_fixture import Services, runtime_inputs, target_for


@pytest.mark.parametrize("outcome", ["succeeded", "failed", "cancelled"])
def test_shared_runtime_keeps_native_cleanup_after_capture_and_preserves_outcome(
    tmp_path, outcome
):
    inputs, manifest = runtime_inputs(tmp_path)
    services = Services(
        tmp_path, failed=outcome == "failed", pending=outcome == "cancelled"
    )
    with RuntimeControlPlane(target_for(manifest)) as runtime:
        experiment_id = runtime.admit_experiment(inputs, services=services)
        for _ in range(40):
            progress = runtime.advance_experiment(experiment_id)
            if outcome == "cancelled" and progress.state == "pending":
                runtime.cancel_experiment(experiment_id)
            results = runtime.experiment_results(experiment_id)
            if results:
                break
        run = runtime.get_run(
            "run:" + inputs.plan.entries[progress.plan_entry_id].run_id
        )
        assert results, (
            progress.state,
            services.events,
            [
                (
                    record.status.state,
                    [(item.code, item.message) for item in record.status.diagnostics],
                )
                for record in run._store.load_records().values()
            ],
        )
        receipt = results[0].cleanup_receipt
        assert receipt.trial_outcome == outcome
        assert receipt.cleanup_status == "succeeded"
        assert services.events[:3] == ["configure", "capture", "cleanup"]


def test_cleanup_failure_still_retains_a_trial_result_and_blocks_later_dispatch(
    tmp_path,
):
    inputs, manifest = runtime_inputs(tmp_path)
    services = Services(tmp_path, cleanup_fails=True)
    with RuntimeControlPlane(target_for(manifest)) as runtime:
        experiment_id = runtime.admit_experiment(inputs, services=services)
        for _ in range(30):
            progress = runtime.advance_experiment(experiment_id)
            if progress.state == "cleanup-failed":
                break
        results = runtime.experiment_results(experiment_id)
        assert len(results) == 1
        assert results[0].cleanup_receipt.cleanup_status == "failed"
        assert results[0].cleanup_receipt.trial_outcome == "succeeded"
        assert runtime.advance_experiment(experiment_id).state == "cleanup-failed"
        assert services.events.count("configure") == 1
