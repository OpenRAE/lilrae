"""Cleanup completes the closed legacy TechVault receipt history (#1700)."""

from __future__ import annotations

from pathlib import Path

from aptl.core.lab_types import LabResult
from tests.test_lifecycle_cleanup import (
    ACTION_DIR,
    BASELINE,
    LEGACY_DIR,
    LEGACY_DONE_DIR,
    OTHER_DIGEST,
    _Backend,
    _baseline,
    _canonical,
    _install,
    _kept_host_files,
    _legacy,
    _no_installed_providers,
    _Project,
    _provider,
    _started,
    _write_record,
)

TECHVAULT_DIGEST = (
    "sha256:db98a9daa62a092a0c6b001217027d7f4ad489889e95d01050e77f148e8ef29b"
)


# Byte-exact receipt written by an aptl-labs 5.5.0 development build (#601).
RECEIPT_5_5_0 = (
    b'{"admission_id":"f789eb926507311e2db6e35332ac4b0f03b82ef9424d4955efcb758c'
    b'dfe2ddd5","distribution":"aptl-labs","distribution_version":"5.5.0",'
    b'"entry_point":"techvault","pack_id":"techvault","pack_set_digest":'
    b'"sha256:db98a9daa62a092a0c6b001217027d7f4ad489889e95d01050e77f148e8ef29b",'
    b'"pack_version":"0.1.0","schema_version":"aptl-startup-reset-authority/v1"}\n'
)


def _techvault_legacy(root: Path, **overrides: str) -> Path:
    """Write one receipt from the closed legacy TechVault history."""
    fields = {
        "pack_id": "techvault",
        "digest": TECHVAULT_DIGEST,
        "distribution": "aptl-labs",
        "version": "6.0.0",
        "pack_version": "0.1.0",
        **overrides,
    }
    return _legacy(root, **fields)


def test_old_techvault_receipts_complete_without_old_distribution(
    tmp_path: Path, monkeypatch
) -> None:
    from aptl.core.lifecycle_cleanup import run_pending_cleanup

    _no_installed_providers(monkeypatch)
    receipts = [
        _write_record(tmp_path, LEGACY_DIR, RECEIPT_5_5_0),
        _techvault_legacy(tmp_path, digest=OTHER_DIGEST, version="6.0.0"),
        _techvault_legacy(tmp_path, pack_id="techvault-participant-study", version="6.0.0"),
    ]
    original = {path: path.read_bytes() for path in receipts}
    baseline = _baseline(tmp_path)

    report = run_pending_cleanup(tmp_path, object())

    assert report.pending == ()
    assert report.completed == 3
    assert not baseline.exists()
    assert {path: path.read_bytes() for path in receipts} == original
    assert sorted(p.name for p in (tmp_path / LEGACY_DONE_DIR).iterdir()) == sorted(
        path.name for path in receipts
    )
    again = run_pending_cleanup(tmp_path, object())
    assert (again.completed, again.pending) == (0, ())


def test_interrupted_cleanup_retries_to_one_recorded_completion(
    tmp_path: Path, monkeypatch
) -> None:
    from aptl.core import lifecycle_cleanup, startup_reset_state

    _no_installed_providers(monkeypatch)
    receipt = _write_record(tmp_path, LEGACY_DIR, RECEIPT_5_5_0)
    baseline = _baseline(tmp_path)
    real_complete = startup_reset_state.complete_pending_cleanup

    def crash_after_effect(*_args: object) -> None:
        raise OSError("interrupted before the completion marker")

    monkeypatch.setattr(
        lifecycle_cleanup, "complete_pending_cleanup", crash_after_effect
    )
    first = lifecycle_cleanup.run_pending_cleanup(tmp_path, object())

    assert not baseline.exists()
    assert [item.reason for item in first.pending] == ["completion-record-failed"]
    assert not (tmp_path / LEGACY_DONE_DIR).exists()

    monkeypatch.setattr(lifecycle_cleanup, "complete_pending_cleanup", real_complete)
    second = lifecycle_cleanup.run_pending_cleanup(tmp_path, object())
    third = lifecycle_cleanup.run_pending_cleanup(tmp_path, object())

    assert (second.completed, second.pending) == (1, ())
    assert (third.completed, third.pending) == (0, ())
    assert [p.name for p in (tmp_path / LEGACY_DONE_DIR).iterdir()] == [receipt.name]


def test_absent_host_state_is_complete(tmp_path: Path, monkeypatch) -> None:
    from aptl.core.lifecycle_cleanup import run_pending_cleanup

    _no_installed_providers(monkeypatch)
    _techvault_legacy(tmp_path)

    report = run_pending_cleanup(tmp_path, object())

    assert (report.completed, report.pending) == (1, ())
    assert not (tmp_path / ".aptl/realization").exists()


def test_symlinked_baseline_is_refused_and_stays_pending(
    tmp_path: Path, monkeypatch
) -> None:
    from aptl.core.lifecycle_cleanup import run_pending_cleanup

    _no_installed_providers(monkeypatch)
    _techvault_legacy(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("keep\n", encoding="utf-8")
    link = tmp_path / BASELINE
    link.parent.mkdir(parents=True)
    link.symlink_to(outside)

    report = run_pending_cleanup(tmp_path, object())

    assert [item.reason for item in report.pending] == ["host-state-unsafe"]
    assert outside.read_text(encoding="utf-8") == "keep\n"
    assert link.is_symlink()
    assert not (tmp_path / LEGACY_DONE_DIR).exists()


def test_malformed_records_stay_pending_without_hiding_valid_work(
    tmp_path: Path, monkeypatch
) -> None:
    from aptl.core.lifecycle_cleanup import run_pending_cleanup

    _no_installed_providers(monkeypatch)
    valid = _techvault_legacy(tmp_path)
    tampered = tmp_path / LEGACY_DIR / ("d" * 64 + ".json")
    tampered.write_bytes(b'{"schema_version":"aptl-startup-reset-authority/v1"}\n')
    stray = tmp_path / LEGACY_DIR / "notes.txt"
    stray.write_bytes(b"left by hand\n")
    unknown = _write_record(
        tmp_path,
        ACTION_DIR,
        _canonical(
            {
                "schema_version": "aptl-lifecycle-cleanup-action/v1",
                "action": "aptl.future-thing.clear",
                "action_version": "1",
                "admission_id": "e" * 64,
                "distribution": "",
                "distribution_version": "",
                "entry_point": "",
                "pack_id": "",
                "pack_set_digest": "",
                "pack_version": "",
            }
        ),
    )
    other = _techvault_legacy(tmp_path, digest=OTHER_DIGEST)
    bad_marker = tmp_path / LEGACY_DONE_DIR / other.name
    bad_marker.parent.mkdir(parents=True)
    bad_marker.write_bytes(b"{}\n")
    before = {
        path: path.read_bytes()
        for path in (tampered, stray, unknown, other, bad_marker)
    }

    report = run_pending_cleanup(tmp_path, object())

    assert report.completed == 1
    assert (tmp_path / LEGACY_DONE_DIR / valid.name).exists()
    assert sorted((item.record, item.reason) for item in report.pending) == sorted(
        [
            (f"startup-reset-v1/{'d' * 12}", "cleanup-record-malformed"),
            ("startup-reset-v1/notes.txt", "cleanup-record-malformed"),
            (f"cleanup-actions-v1/{unknown.name[:12]}", "cleanup-action-unsupported"),
            (f"startup-reset-v1/{other.name[:12]}", "cleanup-record-malformed"),
        ]
    )
    assert {path: path.read_bytes() for path in before} == before


def test_stop_reports_pending_host_cleanup_after_verified_volume_removal(
    tmp_path: Path, monkeypatch
) -> None:
    from aptl.core.lab import stop_lab

    _install(monkeypatch, ("2.0.0", _provider(reset=lambda _context: None)))
    _legacy(
        tmp_path,
        pack_id="otherpack",
        digest=OTHER_DIGEST,
        distribution="otherpack-adapter",
        version="1.0.0",
    )
    _techvault_legacy(tmp_path)
    baseline = _baseline(tmp_path)

    result = stop_lab(
        remove_volumes=True,
        project_dir=tmp_path,
        backend=_Backend(LabResult(success=True)),
    )

    assert result.success is False
    assert result.error.startswith("[lifecycle-host-cleanup-pending]")
    assert "Docker teardown completed" in result.error
    assert "1 host-side cleanup action remains pending" in result.error
    assert "pack.reset for otherpack 1.0.0" in result.error
    assert "provider-reset-authority-unavailable" in result.error
    assert "lilrae lab stop -v --yes" in result.error
    # Independent APTL-owned work still completed.
    assert not baseline.exists()


def test_stop_distinguishes_docker_failure_from_pending_host_cleanup(
    tmp_path: Path, monkeypatch
) -> None:
    from aptl.core.lab import stop_lab

    _no_installed_providers(monkeypatch)
    _techvault_legacy(tmp_path)
    baseline = _baseline(tmp_path)

    result = stop_lab(
        remove_volumes=True,
        project_dir=tmp_path,
        backend=_Backend(LabResult(success=False, error="volume still in use")),
    )

    assert result.success is False
    assert result.error.startswith("[lifecycle-docker-teardown-failed]")
    assert "volume still in use" in result.error
    assert "Host-side cleanup was not attempted" in result.error
    assert "1 action remains pending" in result.error
    assert "lilrae lab stop -v --yes" in result.error
    assert baseline.exists()
    assert not (tmp_path / LEGACY_DONE_DIR).exists()


def test_repeat_stop_finishes_pending_cleanup_when_docker_is_already_gone(
    tmp_path: Path, monkeypatch
) -> None:
    from aptl.core.lab import stop_lab

    _no_installed_providers(monkeypatch)
    _write_record(tmp_path, LEGACY_DIR, RECEIPT_5_5_0)
    baseline = _baseline(tmp_path)
    backend = _Backend(LabResult(success=True))

    first = stop_lab(remove_volumes=True, project_dir=tmp_path, backend=backend)
    second = stop_lab(remove_volumes=True, project_dir=tmp_path, backend=backend)

    assert first.success is True
    assert second.success is True
    assert not baseline.exists()
    assert len(list((tmp_path / LEGACY_DONE_DIR).iterdir())) == 1


def test_reset_removes_the_project_and_finishes_pending_cleanup(
    tmp_path: Path, monkeypatch
) -> None:
    """`lilrae lab reset` is the project-scoped `stop -v` with its records (#1218)."""
    from aptl.core.lab import reset_lab
    from aptl.core.startup_reset_state import load_pending_cleanup

    _no_installed_providers(monkeypatch)
    kept = _kept_host_files(tmp_path)
    _started(tmp_path)
    _techvault_legacy(tmp_path)
    baseline = _baseline(tmp_path)
    project = _Project()

    outcome = reset_lab(tmp_path, backend=project)

    assert outcome.result.success is True
    assert (outcome.containers_found, outcome.networks_found) == (3, 2)
    assert [remove_volumes for _profiles, remove_volumes in project.calls] == [True]
    assert not baseline.exists()
    runnable, rejected = load_pending_cleanup(tmp_path)
    assert (runnable, rejected) == ((), ())
    assert {path: path.read_bytes() for path in kept} == kept


def test_repeated_reset_is_safe(tmp_path: Path, monkeypatch) -> None:
    from aptl.core.lab import reset_lab

    _no_installed_providers(monkeypatch)
    _started(tmp_path)
    _techvault_legacy(tmp_path)
    _baseline(tmp_path)
    project = _Project()

    first = reset_lab(tmp_path, backend=project)
    second = reset_lab(tmp_path, backend=project)

    assert first.result.success is True
    assert second.result.success is True
    assert (second.containers_found, second.networks_found) == (0, 0)
    assert len(list((tmp_path / LEGACY_DONE_DIR).iterdir())) == 1


def test_techvault_adapter_no_longer_owns_aptl_host_state() -> None:
    from aptl_techvault.startup import TechVaultStartupProvider

    assert not hasattr(TechVaultStartupProvider, "reset")


def test_invalid_completion_markers_are_reported_not_ignored(
    tmp_path: Path, monkeypatch
) -> None:
    from aptl.core.lifecycle_cleanup import run_pending_cleanup

    _no_installed_providers(monkeypatch)
    done = tmp_path / LEGACY_DONE_DIR
    done.mkdir(parents=True)
    stray = done / "hand-edited.json"
    stray.write_bytes(b"{}\n")
    orphan = done / ("9" * 64 + ".json")
    orphan.write_bytes(b"{}\n")
    valid = _techvault_legacy(tmp_path)

    report = run_pending_cleanup(tmp_path, object())

    assert report.completed == 1
    assert (done / valid.name).exists()
    assert sorted((item.record, item.reason) for item in report.pending) == [
        (f"startup-reset-completed-v1/{'9' * 12}", "cleanup-record-malformed"),
        ("startup-reset-completed-v1/hand-edited.json", "cleanup-record-malformed"),
    ]
    assert stray.read_bytes() == orphan.read_bytes() == b"{}\n"
