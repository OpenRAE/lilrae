"""Bounded snapshots refuse excessive work before archive publication."""

import pytest

from aptl.core.runstore import LocalRunStore


@pytest.mark.parametrize("limit", ["file", "total", "count"])
def test_snapshot_limits_refuse_incomplete_inventory(tmp_path, limit):
    store = LocalRunStore(tmp_path / "runs")
    store.write_file("run-a", "first.bin", b"12345")
    store.write_file("run-a", "second.bin", b"67890")
    from aptl.core.archival.snapshot import SnapshotLimits, snapshot_run_files

    selected = {
        "file": {"max_file_bytes": 4},
        "total": {"max_total_bytes": 9},
        "count": {"max_files": 1},
    }[limit]
    with pytest.raises(ValueError, match="trial-archive-"):
        snapshot_run_files(store, "run-a", limits=SnapshotLimits(**selected))
