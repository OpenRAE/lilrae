"""A sealed trial lists each piece of required trial data that is missing."""

import json
from types import SimpleNamespace

from aptl.core.trial_record import required_data_gaps


def _participant(address, status="completed"):
    return SimpleNamespace(address=address, status=status)


def test_a_complete_trial_has_no_gaps_and_each_missing_piece_is_named(tmp_path):
    record = SimpleNamespace(
        participants=(_participant("agents.red"), _participant("agents.blue"))
    )
    for address in ("agents.red", "agents.blue"):
        (tmp_path / "trial/transcripts").mkdir(parents=True, exist_ok=True)
        (tmp_path / f"trial/transcripts/{address}.json").write_text("{}")
    (tmp_path / "trial/audit").mkdir(parents=True)
    (tmp_path / "trial/audit/status.json").write_text(
        json.dumps({"status": "captured"})
    )
    (tmp_path / "trial/soc").mkdir(parents=True)
    (tmp_path / "trial/soc/manifest.json").write_text(
        json.dumps({"misp": {"status": "captured"}})
    )
    assert required_data_gaps(tmp_path, record) == []

    (tmp_path / "trial/transcripts/agents.blue.json").unlink()
    (tmp_path / "trial/audit/status.json").write_text(json.dumps({"status": "failed"}))
    (tmp_path / "trial/soc/manifest.json").write_text(
        json.dumps(
            {
                "misp": {"status": "captured"},
                "wazuh-indexer.ndjson": {"status": "failed"},
            }
        )
    )
    record = SimpleNamespace(
        participants=(_participant("agents.red", "failed"), _participant("agents.blue"))
    )
    assert required_data_gaps(tmp_path, record) == [
        "participant agents.red ended failed",
        "raw chat of agents.blue is missing",
        "the host audit log was not captured",
        "trial-end source wazuh-indexer.ndjson was not captured",
    ]
