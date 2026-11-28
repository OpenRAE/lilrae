"""Behavior of the Python release that the Go SSH port preserves."""

import os
import shutil
import stat
from pathlib import Path
from unittest.mock import patch

import asyncssh
import pytest

from aptl.core.host_keys import pin_terminal_host_keys
from aptl.core.snapshot import SSHEndpoint
from aptl.core.ssh import (
    ensure_pivot_key,
    ensure_ssh_keys,
    ensure_target_authorized_keys,
    ensure_victim_authorized_keys,
    ensure_workstation_pivot_key,
)


def _check_pair(path: Path, comment: str) -> str:
    private = asyncssh.read_private_key(path)
    public_path = path.with_suffix(".pub")
    public = asyncssh.read_public_key(public_path)
    assert private.get_algorithm() == "ssh-ed25519"
    assert private.get_comment() == public.get_comment() == comment
    assert private.public_data == public.public_data
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(public_path.stat().st_mode) == 0o644
    return public_path.read_text(encoding="utf-8")


@pytest.mark.skipif(
    shutil.which("ssh-keygen") is None, reason="Python release requires OpenSSH"
)
def test_key_files_and_authorization(tmp_path, request):
    """The release writes three distinct pairs with fixed names and comments."""
    if os.name == "posix":
        mask = os.umask(0o022)
        request.addfinalizer(lambda: os.umask(mask))
    host_ssh = tmp_path / "home" / ".ssh"
    keys = tmp_path / "keys"
    pivot = tmp_path / "config" / "lab-ssh"
    assert ensure_ssh_keys(keys, host_ssh).generated
    assert ensure_pivot_key(pivot).generated
    assert ensure_workstation_pivot_key(pivot).generated
    control = _check_pair(host_ssh / "aptl_lab_key", "aptl-local-lab")
    kali = _check_pair(pivot / "kali_pivot_key", "aptl-kali-pivot")
    workstation = _check_pair(pivot / "workstation_pivot_key", "aptl-workstation-pivot")
    assert len({control.split()[1], kali.split()[1], workstation.split()[1]}) == 3
    assert ensure_target_authorized_keys(keys, pivot).success
    assert ensure_victim_authorized_keys(keys, pivot).success
    assert (keys / "aptl_lab_key.pub").read_text(encoding="utf-8") == control
    assert (keys / "authorized_keys").read_text(encoding="utf-8") == control
    assert (keys / "target_authorized_keys").read_text(
        encoding="utf-8"
    ) == control + kali
    assert (keys / "victim_authorized_keys").read_text(encoding="utf-8") == (
        control + kali + workstation
    )
    reused = ensure_ssh_keys(keys, host_ssh)
    assert reused.success
    assert not reused.generated
    assert (host_ssh / "aptl_lab_key.pub").read_text(encoding="utf-8") == control


def test_start_replaces_pins(tmp_path):
    """A later start replaces changed keys and drops unreachable endpoints."""
    endpoints = [
        SSHEndpoint(name="fixed", host="192.0.2.1", port=22, user="labadmin"),
        SSHEndpoint(name="alternate", host="192.0.2.2", port=2027, user="labadmin"),
    ]
    first = asyncssh.generate_private_key("ssh-ed25519").convert_to_public()
    changed = asyncssh.generate_private_key("ssh-ed25519").convert_to_public()
    client_key = tmp_path / "unused"

    with patch("aptl.core.host_keys._capture_host_key", return_value=first):
        result = pin_terminal_host_keys(tmp_path, endpoints, client_key)
    assert result.pinned == ["fixed", "alternate"]
    assert result.path.read_bytes().splitlines() == [
        b"192.0.2.1 " + first.export_public_key().strip(),
        b"[192.0.2.2]:2027 " + first.export_public_key().strip(),
    ]

    with patch(
        "aptl.core.host_keys._capture_host_key",
        side_effect=[changed, OSError("connection refused")],
    ):
        result = pin_terminal_host_keys(tmp_path, endpoints, client_key)
    assert result.pinned == ["fixed"]
    assert result.failed == ["alternate"]
    assert result.path.read_bytes().splitlines() == [
        b"192.0.2.1 " + changed.export_public_key().strip(),
    ]
