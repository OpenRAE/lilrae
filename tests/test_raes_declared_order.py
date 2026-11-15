"""Readback lists observed records in the declared order."""

from aptl.backends._raes_declared_order import in_declared_order


def test_observed_records_follow_the_declared_order():
    declared = {"ship_targets": [{"target_id": "b", "port": 1514}, {"target_id": "a", "port": 1515}]}
    observed = {"ship_targets": [{"target_id": "a", "port": 1515}, {"target_id": "b", "port": 1514}]}
    assert in_declared_order(observed, declared) == declared
    files = [{"path": "/root/root.txt"}, {"path": "/var/log/x"}]
    assert in_declared_order(list(reversed(files)), files) == files
    # Without a shared unique identity, the observed order stays.
    unnamed = [{"mode": "0600"}, {"mode": "0600"}]
    assert in_declared_order(unnamed, [{"mode": "0600"}]) == unnamed
    # An observed record that the scenario does not declare goes last.
    assert in_declared_order([{"path": "/extra"}, *files], files)[-1] == {"path": "/extra"}
