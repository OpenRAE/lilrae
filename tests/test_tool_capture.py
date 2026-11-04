"""Capture observes runtime-issued tool dispatch without granting authority."""

from threading import Event

import pytest

from aptl.backends.participant_tools.session import LilraeToolSession
from aptl.workbench.process import AgentExecutionError
from tests.test_lilrae_participant_tools import binding, port, result


def test_tool_capture_retains_args_results_timing_and_native_action_identity():
    records = []
    session = LilraeToolSession(
        port(), (binding(),), Event(), evidence_sink=records.append
    )
    session.invoke(
        "aptl-red", "kali_run_command", {"command": "id"}, "call", lambda args: result()
    )
    assert [row["phase"] for row in records] == [
        "proposed",
        "admitted",
        "dispatched",
        "succeeded",
    ]
    assert records[0]["arguments"] == {"command": "id"}
    assert records[-1]["result"] == result()
    assert records[2]["action_instance_id"].startswith("action-")
    assert records[-1]["invocation_id"] == "outer-red"
    assert records[-1]["participant_address"] == "participant.behavior.red"
    assert records[-1]["episode_id"] == "episode-red"
    assert all(row["observed_at"] and row["monotonic_ns"] > 0 for row in records)


def test_capture_failure_before_dispatch_prevents_native_effects():
    effects = []

    def unavailable(row):
        raise OSError("private-storage-details")

    session = LilraeToolSession(
        port(), (binding(),), Event(), evidence_sink=unavailable
    )
    with pytest.raises(AgentExecutionError) as error:
        session.invoke(
            "aptl-red",
            "kali_run_command",
            {"command": "id"},
            "call",
            lambda args: effects.append(args),
        )
    assert effects == []
    assert "private-storage-details" not in str(error.value)


def test_unknown_outcome_is_retained_and_cannot_be_counted_as_success():
    records = []
    session = LilraeToolSession(
        port(), (binding(),), Event(), evidence_sink=records.append
    )

    def native(args):
        raise TimeoutError("private-native-error")

    with pytest.raises(AgentExecutionError):
        session.invoke(
            "aptl-red", "kali_run_command", {"command": "id"}, "call", native
        )
    assert records[-1]["phase"] == "unsettled"
    assert "private-native-error" not in repr(records)
