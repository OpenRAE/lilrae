"""Selected raw file lines belong to the requested trial window."""

from subprocess import CompletedProcess
from types import SimpleNamespace
import json
import pytest
from aptl.core.evidence.adapters.builtins import ContainerFileSource
from aptl.core.evidence.adapters.sources import source_result_to_outcome
from aptl.core.evidence.outcomes import CollectorStatus
from tests.test_evidence_coordinator import _binding, _acquire, _FakeCollector


@pytest.mark.parametrize("missing_history", [False, True])
def test_selected_current_and_rotated_files_exclude_other_trial_records(
    tmp_path, missing_history
):
    paths = [("soc", "/var/log/events"), ("soc", "/var/log/events.1")]

    def read(container, command, **kwargs):
        if missing_history and command[-1].endswith(".1"):
            return CompletedProcess(command, 1, "", "file missing")
        return CompletedProcess(
            command,
            0,
            '{"timestamp":"2026-11-03T00:00:00Z","event":"older trial"}\n'
            '{"timestamp":"2026-11-04T00:00:10Z","event":"requested raw event","extra":42}\n'
            '{"timestamp":"2026-11-05T00:00:00Z","event":"later trial"}\n',
            "",
        )

    source = ContainerFileSource(
        SimpleNamespace(container_exec=read),
        paths,
        timestamp_of=lambda line: json.loads(line)["timestamp"],
    )
    result = source.fetch("2026-11-04T00:00:00Z", "2026-11-04T00:01:00Z")
    assert result.status is (
        CollectorStatus.SOURCE_UNAVAILABLE
        if missing_history
        else CollectorStatus.MID_RUN_LOSS
    )
    binding = _binding()
    captured = _acquire(
        tmp_path,
        [binding],
        {
            binding.registration_id: _FakeCollector(
                binding.registration_id,
                outcome=source_result_to_outcome(
                    result, "2026-11-04T00:00:00Z", "2026-11-04T00:01:00Z"
                ),
            )
        },
    )
    retained = (tmp_path / "runs" / "run-1" / captured.refs[0].content_uri).read_bytes()
    assert b"older trial" not in retained
    assert b"later trial" not in retained
    assert b"requested raw event" in retained
    assert b"extra" in retained
    assert b"History coverage" in retained
    if missing_history:
        assert b"source-unavailable" in retained


def test_file_source_requires_a_timestamp_decoder_before_reads():
    with pytest.raises(TypeError, match="timestamp_of"):
        ContainerFileSource(object(), [("soc", "/var/log/events")])


def test_bad_file_line_preserves_peer_and_discloses_gap():
    good = '{"timestamp":"2026-11-04T00:00:10Z","event":"accepted"}\n'
    operations = SimpleNamespace(
        container_exec=lambda *a, **k: CompletedProcess([], 0, good + "malformed\n", "")
    )
    source = ContainerFileSource(
        operations,
        [("soc", "/var/log/events")],
        timestamp_of=lambda line: json.loads(line)["timestamp"],
    )
    result = source.fetch("2026-11-04T00:00:00Z", "2026-11-04T00:01:00Z")
    assert result.records[0]["output"] == good
    assert result.dropped_count == 1
    assert result.status is CollectorStatus.MID_RUN_LOSS
