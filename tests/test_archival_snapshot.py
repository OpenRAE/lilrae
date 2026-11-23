"""Snapshots copy every run file completely before archive publication."""

import hashlib

from aptl.core.runstore import LocalRunStore


def test_snapshot_copies_every_file_completely(tmp_path):
    store = LocalRunStore(tmp_path / "runs")
    large = b"x" * (65 * 1024 * 1024)
    store.write_file("run-a", "first.bin", b"12345")
    store.write_file("run-a", "nested/deeper/second.bin", large)
    from aptl.core.archival.snapshot import snapshot_run_files

    artifacts = snapshot_run_files(store, "run-a")

    assert [item.path for item in artifacts] == [
        "first.bin",
        "nested/deeper/second.bin",
    ]
    second = artifacts[1]
    assert second.size == len(large)
    assert second.sha256 == hashlib.sha256(large).hexdigest()
    assert b"".join(second.chunks()) == large
    assert second.specification().expected_size_bytes == len(large)
