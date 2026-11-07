"""The TechVault enrollment baseline refuses an unsafe write path (#1700)."""


def test_baseline_write_path_rejection_returns_false(monkeypatch, tmp_path):
    from aptl.utils.pathsafe import REASON_SYMLINK, PathContainmentError
    from aptl_techvault.evidence import techvault_enrollment_baseline as baseline

    def reject(*args, **kwargs):
        raise PathContainmentError(REASON_SYMLINK, "private-path-canary")

    monkeypatch.setattr(baseline, "replace_private_nofollow", reject)
    assert baseline.record_enrollment_baseline(tmp_path, {"agent": "001"}) is False
