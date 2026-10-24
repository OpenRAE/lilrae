"""Desktop state follows the admitted range lifecycle, including failures."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from aptl.core import lab
from aptl.core import participant_desktop as desktop
from aptl.core import _participant_desktop_files as files
from aptl.core.lab_types import LabResult


@pytest.fixture
def surface(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    files.write_desktop_files(home, {files.CREDENTIALS_FILE: b"previous logins"})
    ready = home / ".config/aptl/run-ready"
    ready.write_text("ready\n")
    hosts = tmp_path / desktop.HOSTS_RELPATH
    hosts.parent.mkdir(parents=True, mode=0o700)
    hosts.write_text("{}")
    entry = SimpleNamespace(pw_uid=os.geteuid(), pw_gid=os.getegid(), pw_dir=str(home))
    monkeypatch.setenv(desktop.ACCOUNT_VARIABLE, "participant")
    monkeypatch.setattr(desktop.pwd, "getpwnam", lambda _name: entry)
    return home / files.DESKTOP_DIR / files.CREDENTIALS_FILE, ready, hosts


def _presence(present=False):
    return SimpleNamespace(
        error=None, present=present, container_count=int(present), network_count=0
    )


def test_empty_admitted_start_withdraws_the_previous_surface(tmp_path, surface):
    backend = SimpleNamespace(observe_project_runtime=lambda: _presence())
    ctx = lab._LabStartContext(project_dir=tmp_path, skip_seed=False, backend=backend)

    assert lab._step_reject_preexisting_range(ctx) is None
    assert not any(path.exists() for path in surface)


def test_refused_second_start_preserves_the_running_surface(tmp_path, surface):
    backend = SimpleNamespace(observe_project_runtime=lambda: _presence(True))
    ctx = lab._LabStartContext(project_dir=tmp_path, skip_seed=False, backend=backend)

    assert not lab._step_reject_preexisting_range(ctx).success
    assert all(path.exists() for path in surface)


def test_failed_admitted_start_withdraws_the_surface(tmp_path, surface):
    backend = SimpleNamespace(observe_project_runtime=lambda: _presence())
    ctx = lab._LabStartContext(project_dir=tmp_path, skip_seed=False, backend=backend)
    ctx.range_was_absent = True

    lab._account_for_failed_start(ctx, LabResult(success=False, error="failed"))

    assert not any(path.exists() for path in surface)


@pytest.mark.parametrize("remove_volumes", [False, True])
def test_stop_and_reset_withdraw_the_surface(
    tmp_path, surface, monkeypatch, remove_volumes
):
    monkeypatch.setattr(
        lab, "_finalize_required_transcript_capture", lambda *_args: None
    )
    monkeypatch.setattr(lab, "_run_pending_host_cleanup", lambda *_args: None)
    backend = SimpleNamespace(stop=lambda *_args, **_kw: LabResult(success=True))

    assert lab._tear_down_owned(
        tmp_path, backend, [], remove_volumes=remove_volumes
    ).success
    assert not any(path.exists() for path in surface)


def test_management_guest_withdrawal_also_clears_privileged_hostnames(
    tmp_path, monkeypatch
):
    from aptl.core import participant_hosts

    calls = []
    monkeypatch.setenv("APTL_SEAT_DESKTOP_HANDOFF", "1")
    monkeypatch.setattr(desktop, "_effective_uid", lambda: 0)
    monkeypatch.setattr(participant_hosts, "clear", lambda: calls.append("clear"))

    desktop.withdraw_participant_desktop(tmp_path, "")

    assert calls == ["clear"]


def test_stop_cannot_report_success_when_desktop_withdrawal_failed(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        lab, "_finalize_required_transcript_capture", lambda *_args: None
    )
    monkeypatch.setattr(desktop, "withdraw_participant_desktop", lambda *_args: False)
    backend = SimpleNamespace(stop=lambda *_args, **_kw: LabResult(success=True))

    result = lab._tear_down_owned(tmp_path, backend, [], remove_volumes=False)

    assert not result.success
    assert "desktop" in result.error.lower()
