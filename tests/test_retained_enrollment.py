"""Trial-bound retained enrollment ids exposed to rebuilt capture sources."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from aptl.backends.scenario_capture import capture_source_context
from aptl.core.lifecycle_cleanup import (
    WAZUH_ENROLLMENT_BASELINE_RELPATH,
    WAZUH_TRIAL_ENROLLMENT_DIR,
    clear_wazuh_enrollment_baseline,
)


def _trial(run_id: str = "run-a") -> SimpleNamespace:
    identity = {"run_id": run_id, "plan_entry_id": "entry-a"}
    return SimpleNamespace(identity=lambda: dict(identity))


def _source(project_dir, trial, *, provisioning: bool = False):
    """Build a fresh capture source context, as a reconstructed source would."""

    request = SimpleNamespace(
        backend=object(),
        realization=SimpleNamespace(nodes=()),
        environment={},
        capture_selection=SimpleNamespace(
            contribution=SimpleNamespace(runtime_environment_keys=()),
            context=SimpleNamespace(trial=trial),
        ),
        project_dir=project_dir,
    )
    context = capture_source_context(request, establish_enrollment=provisioning)
    return context.retain_enrollment_ids


def _record_path(project_dir):
    return next((project_dir / WAZUH_TRIAL_ENROLLMENT_DIR).iterdir())


def test_rebuilt_source_reads_pre_restart_ids_for_unchanged_and_changed(tmp_path):
    trial = _trial()
    assert _source(tmp_path, trial, provisioning=True)({"db": "001", "web": "002"}) == {}
    prior = _source(tmp_path, trial)({"db": "001", "web": "009"})
    assert dict(prior) == {"db": "001", "web": "002"}
    assert prior["db"] == "001"
    assert prior["web"] != "009"
    assert dict(_source(tmp_path, trial)({})) == {"db": "001", "web": "002"}


def test_a_new_host_is_retained_but_never_proven_by_its_first_observation(tmp_path):
    retain = _source(tmp_path, _trial(), provisioning=True)
    assert retain({"db": "001"}) == {}
    assert dict(retain({"db": "001", "web": "002"})) == {"db": "001"}


def test_only_the_first_provisioning_capture_may_retain_ids(tmp_path):
    trial = _trial()
    _source(tmp_path, trial, provisioning=True)({"db": "001"})
    restarted = _source(tmp_path, trial, provisioning=True)
    assert dict(restarted({"db": "001", "web": "002"})) == {"db": "001"}
    assert dict(_source(tmp_path, trial)({})) == {"db": "001"}


def test_ids_first_seen_after_provisioning_never_become_a_baseline(tmp_path):
    trial = _trial()
    _source(tmp_path, trial, provisioning=True)({})
    for _ in range(2):
        assert _source(tmp_path, trial)({"db": "009"}) == {}
        assert _source(tmp_path, trial, provisioning=True)({"db": "009"}) == {}


def _provision(project_dir, trial, seen):
    """Run the provisioning capture once, as each lab start does."""

    from aptl.backends.raes_evidence_acquisition import (
        NativeEvidenceRequest,
        acquire_native_evidence,
    )
    from aptl.core.experiment.capture_plan import empty_capture_plan
    from aptl.core.runstore import LocalRunStore

    selection = SimpleNamespace(
        context=SimpleNamespace(trial=trial),
        contribution=SimpleNamespace(
            native_registration_ids=frozenset({"example.events"}),
            runtime_environment_keys=(),
            runtime_adapter=SimpleNamespace(native_sources=lambda _context: {}),
        ),
    )
    request = NativeEvidenceRequest(
        empty_capture_plan(),
        object(),
        SimpleNamespace(nodes=()),
        project_dir,
        {},
        LocalRunStore(project_dir / "archive"),
        trial.identity()["run_id"],
        selection,
    )
    acquire_native_evidence(request)
    return seen.pop()


def test_missing_earlier_evidence_stays_unproven_across_restart(
    tmp_path, monkeypatch
):
    from aptl.backends import scenario_capture

    seen = []

    def sources(
        request,
        *,
        establish_enrollment=False,
        phase=scenario_capture.AcquisitionPhase.MEASUREMENT,
    ):
        context = scenario_capture.capture_source_context(
            request, establish_enrollment=establish_enrollment, phase=phase
        )
        seen.append(context.retain_enrollment_ids)
        return {}

    monkeypatch.setattr(scenario_capture, "family_capture_sources", sources)
    monkeypatch.setattr(
        "aptl.backends._raes_native_evidence_acquisition.acquire_evidence",
        lambda **kw: None,
    )
    trial = _trial()
    assert _provision(tmp_path, trial, seen)({"db": "001"}) == {}
    assert dict(_provision(tmp_path, trial, seen)({"db": "001"})) == {"db": "001"}
    _record_path(tmp_path).unlink()
    for _ in range(2):
        assert _provision(tmp_path, trial, seen)({"db": "009"}) is None
        assert _source(tmp_path, trial)({"db": "009"}) is None
    assert list((tmp_path / WAZUH_TRIAL_ENROLLMENT_DIR).iterdir()) == []


def test_evidence_from_another_trial_is_not_visible(tmp_path):
    _source(tmp_path, _trial("run-a"), provisioning=True)({"db": "001"})
    assert _source(tmp_path, _trial("run-b"))({"db": "001"}) is None
    assert _source(tmp_path, _trial("run-b"), provisioning=True)({"db": "002"}) == {}
    assert dict(_source(tmp_path, _trial("run-a"))({})) == {"db": "001"}
    assert dict(_source(tmp_path, _trial("run-b"))({})) == {"db": "002"}


@pytest.mark.parametrize("content", [b"not json", b'{"db": 1}', b"[]"])
def test_invalid_retained_evidence_is_unproven_and_not_replaced(tmp_path, content):
    trial = _trial()
    _source(tmp_path, trial, provisioning=True)({})
    path = _record_path(tmp_path)
    path.write_bytes(content)
    assert _source(tmp_path, trial)({"db": "001"}) is None
    assert path.read_bytes() == content


def test_unreadable_retained_evidence_is_unproven(tmp_path):
    trial = _trial()
    _source(tmp_path, trial, provisioning=True)({})
    path = _record_path(tmp_path)
    path.unlink()
    (tmp_path / "elsewhere.json").write_text('{"db": "001"}')
    path.symlink_to(tmp_path / "elsewhere.json")
    assert _source(tmp_path, trial)({"db": "001"}) is None


def test_duplicate_ids_are_unproven_and_not_retained(tmp_path):
    trial = _trial()
    retain = _source(tmp_path, trial, provisioning=True)
    assert retain({"db": "001", "web": "001"}) is None
    assert retain({}) == {}
    retain({"db": "001"})
    assert retain({"db": "001", "web": "001"}) is None
    assert _source(tmp_path, trial)({"db": "001", "web": "001"}) is None
    assert dict(_source(tmp_path, trial)({})) == {"db": "001"}


def test_retained_duplicate_ids_are_unproven_after_reconstruction(tmp_path):
    trial = _trial()
    _source(tmp_path, trial, provisioning=True)({})
    _record_path(tmp_path).write_text('{"db": "001", "web": "001"}')
    assert _source(tmp_path, trial)({"db": "001", "web": "002"}) is None


@pytest.mark.parametrize(
    "observed", [{"db": "001\n"}, {"../db": "001"}, {"db": ""}, ["db"]]
)
def test_invalid_observations_are_refused(tmp_path, observed):
    retain = _source(tmp_path, _trial(), provisioning=True)
    assert retain(observed) is None
    assert retain({}) == {}


def test_volume_reset_cleanup_clears_trial_evidence(tmp_path):
    trial = _trial()
    clear_wazuh_enrollment_baseline(tmp_path)
    _source(tmp_path, trial, provisioning=True)({"db": "001"})
    clear_wazuh_enrollment_baseline(tmp_path)
    assert not (tmp_path / WAZUH_TRIAL_ENROLLMENT_DIR).exists()
    assert _source(tmp_path, trial)({}) is None


def test_retained_ids_are_read_only(tmp_path):
    retained = _source(tmp_path, _trial(), provisioning=True)({"db": "001"})
    with pytest.raises(TypeError):
        retained["db"] = "002"


# --- Scenario record for a context without a trial (#1705) ---


def _scenario_record(project_dir):
    return project_dir / WAZUH_ENROLLMENT_BASELINE_RELPATH


def test_a_context_without_a_trial_uses_the_legacy_scenario_record(tmp_path):
    retain = _source(tmp_path, None, provisioning=True)
    assert retain({"db": "001"}) == {}
    assert json.loads(_scenario_record(tmp_path).read_text()) == {"db": "001"}
    assert dict(_source(tmp_path, None)({})) == {"db": "001"}
    assert not (tmp_path / WAZUH_TRIAL_ENROLLMENT_DIR).exists()


def test_measurement_cannot_make_or_repair_the_scenario_record(tmp_path):
    assert _source(tmp_path, None)({"db": "001"}) is None
    assert not _scenario_record(tmp_path).exists()
    _source(tmp_path, None, provisioning=True)({})
    assert _source(tmp_path, None)({"db": "001"}) == {}
    assert dict(_source(tmp_path, None)({})) == {}


def test_a_later_startup_adds_new_hosts_but_never_replaces_an_id(tmp_path):
    _source(tmp_path, None, provisioning=True)({"db": "001"})
    later = _source(tmp_path, None, provisioning=True)
    assert dict(later({"db": "009", "web": "002"})) == {"db": "001"}
    assert dict(_source(tmp_path, None)({})) == {"db": "001", "web": "002"}


def test_a_legacy_baseline_is_read_and_an_invalid_one_is_not_replaced(tmp_path):
    record = _scenario_record(tmp_path)
    record.parent.mkdir(parents=True)
    record.write_text('{"db":"001"}\n')
    assert dict(_source(tmp_path, None)({"db": "009"})) == {"db": "001"}
    record.write_text('{"db": "001", "web": "001"}')
    assert _source(tmp_path, None, provisioning=True)({"ad": "003"}) is None
    assert record.read_text() == '{"db": "001", "web": "001"}'


def test_volume_reset_cleanup_clears_the_scenario_record(tmp_path):
    _source(tmp_path, None, provisioning=True)({"db": "001"})
    clear_wazuh_enrollment_baseline(tmp_path)
    assert not _scenario_record(tmp_path).exists()
    assert _source(tmp_path, None)({}) is None


def test_an_unsafe_scenario_record_write_is_unproven(tmp_path, monkeypatch):
    from aptl.core import retained_enrollment
    from aptl.utils.pathsafe import REASON_SYMLINK, PathContainmentError

    _source(tmp_path, None, provisioning=True)({})

    def reject(*args, **kwargs):
        raise PathContainmentError(REASON_SYMLINK, "private-path-canary")

    monkeypatch.setattr(retained_enrollment, "replace_private_nofollow", reject)
    assert _source(tmp_path, None, provisioning=True)({"db": "001"}) is None
    assert dict(_source(tmp_path, None)({})) == {}
