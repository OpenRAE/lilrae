"""Kali broker chains pass the TechVault transcript verifier (#1700)."""

from __future__ import annotations

import base64
import signal
import stat

import pytest

from aptl_techvault.evidence.techvault import (
    TranscriptFrame,
    transcript_chain_digest,
)
from tests.test_kali_capture_broker import _prepare_broker_session, broker


def test_recorder_writes_ordered_directional_frames_and_chain(broker, tmp_path):
    authority = {
        "run_id": "run-1",
        "plan_id": "capture-plan-1",
        "binding_id": "aptl.collector.redteam-session-transcript",
        "activated_at": "2026-09-14T10:00:00Z",
    }
    instants = iter(
        (
            "2026-09-14T10:00:01Z",
            "2026-09-14T10:00:02Z",
            "2026-09-14T10:00:03Z",
            "2026-09-14T10:00:04Z",
        )
    )
    recorder = broker.SessionRecorder(
        tmp_path / "captures",
        authority,
        session_id="session-1",
        now=lambda: next(instants),
    )
    recorder.append("input", b"whoami\n")
    recorder.append("output", b"kali\r\n")
    recorder.finish("clean-exit")

    exported = broker.export_capture(tmp_path / "captures", authority)
    assert exported["accepted_session_ids"] == ["session-1"]
    session = exported["sessions"][0]
    assert session["close_reason"] == "clean-exit"
    assert [frame["direction"] for frame in session["frames"]] == [
        "input",
        "output",
    ]
    frames = tuple(
        TranscriptFrame(
            sequence=frame["sequence"],
            timestamp=frame["timestamp"],
            direction=frame["direction"],
            data=base64.b64decode(frame["data_b64"], validate=True),
        )
        for frame in session["frames"]
    )
    assert session["final_chain_digest"] == transcript_chain_digest(frames)
    assert (
        stat.S_IMODE(
            (tmp_path / "captures/run-1/sessions/session-1/metadata.json")
            .stat()
            .st_mode
        )
        == 0o600
    )


@pytest.mark.parametrize(
    "signum", [signal.SIGHUP, signal.SIGTERM], ids=["hangup", "quiesce"]
)
@pytest.mark.parametrize("boundary", ["registration", "ledger", "spawn", "frame"])
def test_teardown_finishes_custody_update_before_finalizing(
    broker, tmp_path, monkeypatch, mocker, signum, boundary
):
    """A signal during acceptance, spawn or recording cannot strand custody."""
    import os
    import signal
    from types import SimpleNamespace

    runtime = _prepare_broker_session(broker, tmp_path, monkeypatch)
    handlers = {}
    monkeypatch.setattr(broker.signal, "signal", handlers.__setitem__)
    write_exclusive = broker._write_exclusive
    append_line = broker._append_line

    def interrupt():
        handlers[signum](signum, None)
        # A second teardown request must preserve the first close reason and
        # must not interrupt the same custody update either.
        other = signal.SIGTERM if signum == signal.SIGHUP else signal.SIGHUP
        handlers[other](other, None)

    def write(path, data, mode=0o600):
        write_exclusive(path, data, mode)
        if boundary == "registration" and path.suffix == ".pid":
            interrupt()

    def append(path, value):
        append_line(path, value)
        if (boundary == "ledger" and path.name == "accepted-sessions.jsonl") or (
            boundary == "frame" and path.name == "frames.jsonl"
        ):
            interrupt()

    monkeypatch.setattr(broker, "_write_exclusive", write)
    monkeypatch.setattr(broker, "_append_line", append)
    child = mocker.Mock(pid=4321)
    child.poll.return_value = None

    def spawn(*_args, **_kwargs):
        if boundary == "spawn":
            interrupt()
        return child

    monkeypatch.setattr(broker.subprocess, "Popen", spawn)
    killed = []
    monkeypatch.setattr(broker.os, "killpg", lambda *args: killed.append(args))
    stdin_read, stdin_write = os.pipe()
    monkeypatch.setattr(broker.sys, "stdin", mocker.Mock(fileno=lambda: stdin_read))
    # Exercise the real relay and recorder with one output frame. The pending
    # signal must wait until both the frame and its chain state are committed.
    selector = mocker.Mock()
    selector.select.return_value = [(SimpleNamespace(fd=-100, data="output"), 1)]
    monkeypatch.setattr(broker.selectors, "DefaultSelector", lambda: selector)
    read = broker.os.read
    monkeypatch.setattr(
        broker.os,
        "read",
        lambda fd, count: b"last output" if fd == -100 else read(fd, count),
    )
    try:
        assert broker.run_broker() == (129 if signum == signal.SIGHUP else 143)
    finally:
        os.close(stdin_read)
        os.close(stdin_write)

    assert not (runtime / "sessions/session-1.pid").exists()
    authority = broker.read_authority(runtime)
    exported = broker.export_capture(tmp_path / "captures", authority)
    assert exported["accepted_session_ids"] == ["session-1"]
    session = exported["sessions"][0]
    expected_reason = "signal" if signum == signal.SIGHUP else "forced-teardown"
    assert session["close_reason"] == expected_reason
    frames = tuple(
        TranscriptFrame(
            sequence=frame["sequence"],
            timestamp=frame["timestamp"],
            direction=frame["direction"],
            data=base64.b64decode(frame["data_b64"], validate=True),
        )
        for frame in session["frames"]
    )
    assert session["final_chain_digest"] == transcript_chain_digest(frames)
    assert session["frame_count"] == (1 if boundary == "frame" else 0)
    expected_kills = [(4321, signal.SIGTERM)] if boundary in {"spawn", "frame"} else []
    assert killed == expected_kills
    assert handlers[signal.SIGTERM] is signal.SIG_IGN
    assert handlers[signal.SIGHUP] is signal.SIG_IGN
