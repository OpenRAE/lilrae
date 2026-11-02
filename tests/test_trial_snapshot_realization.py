"""Exact snapshot, processor scope and protected archive regressions (#1415)."""

from dataclasses import replace
from types import SimpleNamespace
import json
import stat

import pytest
from raes_contracts.run_scope import PlanScope

from aptl.backends._raes_planning_entry import planning_run_scope
from aptl.backends._raes_start_run import admitted_run_target
from aptl.backends.scenario_family import FamilyTrialInput, admit_family_trial
from aptl.core.config import AptlConfig
from aptl.core.runstore import LocalRunStore
from tests.test_family_adapter_contract import BACKEND
from tests.test_family_adapter_contract import family_input as family_input


@pytest.fixture
def trial_bundle(family_input):
    bundle, family, plan = family_input("/opt/b")
    trial = admit_family_trial(
        bundle, BACKEND, FamilyTrialInput(plan, "entry-a", family)
    )
    return replace(bundle, trial=trial), family, plan


def test_supplied_snapshot_must_match_the_sealed_entry(trial_bundle):
    bundle, family, plan = trial_bundle
    request = FamilyTrialInput(plan, "entry-a", family, snapshot=bundle.trial.snapshot)
    assert (
        admit_family_trial(bundle, BACKEND, request).snapshot == bundle.trial.snapshot
    )
    wrong = replace(request, snapshot=request.snapshot.replace(b"/opt/b", b"/opt/a"))
    with pytest.raises(ValueError, match="^family-trial-invalid$"):
        admit_family_trial(bundle, BACKEND, wrong)


def test_scope_adopts_run_and_entry_and_rejects_overrides(trial_bundle):
    bundle, _, _ = trial_bundle
    provenance = bundle.trial.provenance
    scope = planning_run_scope(bundle)
    assert (scope.run_id, scope.instantiation_id) == (
        provenance.run_id,
        provenance.plan_entry_id,
    )
    for requested in (PlanScope(run_id="other"), PlanScope(instantiation_id="other")):
        with pytest.raises(ValueError, match="^family-(run|entry)-identity-mismatch$"):
            planning_run_scope(bundle, requested)


def test_start_adopts_preallocated_run_without_an_explicit_target(
    tmp_path, trial_bundle
):
    bundle, _, _ = trial_bundle
    admitted = SimpleNamespace(
        bundle=bundle,
        execution_plan=SimpleNamespace(
            provisioning=SimpleNamespace(materialization_source=None)
        ),
    )
    target = admitted_run_target(admitted, None, tmp_path, AptlConfig())
    assert target.run_id == bundle.trial.provenance.run_id
    assert target.run_store.base_dir == tmp_path / "runs"


def test_archive_preserves_exact_bytes_and_safe_selection_joins(tmp_path, trial_bundle):
    from aptl.backends.scenario_trial_archive import archive_family_trial

    bundle, _, _ = trial_bundle
    store = LocalRunStore(tmp_path / "runs")
    trial = bundle.trial
    archive_family_trial(store, trial)
    archive_family_trial(store, trial)
    root = store.get_run_path(trial.provenance.run_id)
    snapshot = root / "trial/instantiated-snapshot.json"
    assert snapshot.read_bytes() == trial.snapshot
    assert stat.S_IMODE(snapshot.stat().st_mode) == 0o600
    evidence = json.loads((root / "trial/identity.json").read_text())
    assert evidence["trial"] == trial.identity()
    assert evidence["selections"] == [
        {
            "variation_point_id": item.variation_point_id,
            "record_digest": item.record_digest,
        }
        for item in trial.provenance.selections
    ]
    assert "/opt/b" not in json.dumps(evidence)
    snapshot.chmod(0o640)
    with pytest.raises(ValueError, match="^family-trial-archive-conflict$"):
        archive_family_trial(store, trial)
    snapshot.chmod(0o600)
    snapshot.write_bytes(b"conflicting bytes")
    with pytest.raises(ValueError, match="^family-trial-archive-conflict$"):
        archive_family_trial(store, trial)


def test_archive_rejects_a_sealed_run_and_symlink(tmp_path, trial_bundle):
    from aptl.backends.scenario_trial_archive import archive_family_trial

    bundle, _, _ = trial_bundle
    trial = bundle.trial
    store = LocalRunStore(tmp_path / "runs")
    root = store.create_run(trial.provenance.run_id)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "trial").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="^family-trial-archive-failed$"):
        archive_family_trial(store, trial)
    assert list(outside.iterdir()) == []
    (root / "trial").unlink()
    store.commit_seal_marker(trial.provenance.run_id, {"sealed": True})
    with pytest.raises(ValueError, match="^family-trial-run-sealed$"):
        archive_family_trial(store, trial)


def test_start_archives_exact_input_before_apply_and_retains_failed_input(
    monkeypatch, tmp_path, trial_bundle
):
    from aptl.backends import raes
    from aptl.core.lab_types import LabResult

    bundle, _, _ = trial_bundle
    admitted = SimpleNamespace(
        bundle=bundle,
        execution_plan=SimpleNamespace(
            provisioning=SimpleNamespace(materialization_source=None)
        ),
        target=object(),
        participant_delivery_plan=None,
    )
    invoked = []

    def apply(target, plan, path, *, run_store, run_id, runtime_options):
        root = run_store.get_run_path(run_id)
        assert (
            root / "trial/instantiated-snapshot.json"
        ).read_bytes() == bundle.trial.snapshot
        invoked.append(run_id)
        return SimpleNamespace(
            lab_result=LabResult(success=False, error="test apply failure")
        )

    monkeypatch.setattr(raes, "_run_execution_plan", apply)
    result = raes.start_raes_scenario(
        tmp_path, AptlConfig(), object(), admitted=admitted
    )
    assert not result.lab_result.success
    assert invoked == [bundle.trial.provenance.run_id]
    root = tmp_path / "runs" / bundle.trial.provenance.run_id
    assert (root / "trial/identity.json").exists()
    (root / "trial/instantiated-snapshot.json").write_bytes(b"corrupted")
    result = raes.start_raes_scenario(
        tmp_path, AptlConfig(), object(), admitted=admitted
    )
    assert not result.lab_result.success
    assert "family-trial-archive-conflict" in result.lab_result.error
    assert invoked == [bundle.trial.provenance.run_id]


def test_start_contains_storage_failures_before_apply(
    monkeypatch, tmp_path, trial_bundle
):
    from aptl.backends import raes

    bundle, _, _ = trial_bundle
    admitted = SimpleNamespace(
        bundle=bundle,
        execution_plan=SimpleNamespace(
            provisioning=SimpleNamespace(materialization_source=None)
        ),
    )
    monkeypatch.setattr(
        raes,
        "_run_execution_plan",
        lambda *a, **kw: pytest.fail("storage failure must stop apply"),
    )
    from aptl.backends.raes_start_model import AcesRunTarget

    with pytest.raises(ValueError, match="^family-trial-local-storage-required$"):
        from aptl.backends.scenario_trial_archive import archive_family_trial

        archive_family_trial(object(), bundle.trial)
    store = LocalRunStore(tmp_path / "runs")

    def fail(*a, **kw):
        raise OSError("storage failure with sensitive details")

    monkeypatch.setattr(store, "create_run_json_once", fail)
    result = raes.start_raes_scenario(
        tmp_path,
        AptlConfig(),
        object(),
        admitted=admitted,
        run_target=AcesRunTarget(store, bundle.trial.provenance.run_id),
    )
    assert not result.lab_result.success
    assert "family-trial-archive-failed" in result.lab_result.error
    assert "sensitive details" not in result.lab_result.error
