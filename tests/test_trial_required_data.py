"""Fixed filenames cannot substitute for the admitted trial capture plan."""

from types import SimpleNamespace

from aptl.core.trial_record import required_data_gaps


def test_legacy_capture_files_do_not_establish_data_completeness(tmp_path):
    for name in ("trial/transcripts/agents.blue.json", "trial/audit/status.json", "trial/soc/manifest.json"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{}')
    assert required_data_gaps(tmp_path, SimpleNamespace(capture_plan_id=None)) == [
        "the trial has no retained capture plan and acquisition reports"
    ]
