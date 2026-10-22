"""The privileged hostname publisher changes only trusted, bounded inputs."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys

import pytest

from aptl.core import participant_hosts as hosts


def _document(path, *, address="172.31.250.10", hostname="console.example.test"):
    path.write_text(
        json.dumps(
            {
                "schema": hosts.SCHEMA,
                "entries": [
                    {"address": address, "hostname": hostname},
                ],
            }
        )
    )
    path.chmod(0o600)
    return path


@pytest.mark.parametrize("linked_input", [True, False])
def test_publisher_refuses_symlinked_ancestors(tmp_path, linked_input):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    document = _document(real / "input.json")
    target = real / "hosts"
    target.write_text("127.0.0.1 localhost\n")

    with pytest.raises((OSError, ValueError)):
        hosts.publish(
            link / "input.json" if linked_input else document,
            target if linked_input else link / "hosts",
        )

    assert target.read_text() == "127.0.0.1 localhost\n"


@pytest.mark.parametrize("address", ["0.0.0.0", "::", "224.0.0.1", "ff02::1"])
def test_unusable_addresses_are_refused(tmp_path, address):
    document = json.loads(
        _document(tmp_path / "input.json", address=address).read_text()
    )
    with pytest.raises(hosts.HostsPublicationError):
        hosts.validated_entries(document)


def test_publisher_refuses_a_conflicting_unowned_mapping(tmp_path):
    target = tmp_path / "hosts"
    original = "127.0.0.1 localhost\n10.0.0.1 console.example.test # operator\n"
    target.write_text(original)
    target.chmod(0o644)

    with pytest.raises(hosts.HostsPublicationError):
        hosts.publish(_document(tmp_path / "input.json"), target)

    assert target.read_text() == original


def test_clear_removes_owned_entries_and_preserves_metadata(tmp_path):
    target = tmp_path / "hosts"
    target.write_text(
        f"127.0.0.1 localhost\n172.31.250.10 console.example.test {hosts.MARKER}\n"
    )
    target.chmod(0o640)
    before = target.stat()

    assert hosts.main(["publisher", "--clear", str(target)]) == 0

    after = target.stat()
    assert target.read_text() == "127.0.0.1 localhost\n"
    assert stat.S_IMODE(after.st_mode) == 0o640
    assert (after.st_uid, after.st_gid) == (before.st_uid, before.st_gid)


@pytest.mark.parametrize("fifo_input", [True, False])
def test_publisher_rejects_a_fifo_without_waiting_for_a_writer(tmp_path, fifo_input):
    document = tmp_path / "input.json"
    target = tmp_path / "hosts"
    if fifo_input:
        os.mkfifo(document, 0o600)
        target.write_text("127.0.0.1 localhost\n")
    else:
        _document(document)
        os.mkfifo(target, 0o600)

    result = subprocess.run(
        [sys.executable, hosts.__file__, str(document), str(target)],
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 1
    assert "participant hosts file is unsafe" in result.stderr
