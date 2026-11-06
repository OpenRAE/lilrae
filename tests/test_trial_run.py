"""A trial seals under caller IDs and stops at its deadline or on request (#1670)."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aptl.core.archival import verify_sealed_archive
from aptl.core.runstore import LocalRunStore
from aptl.core.trial_attempt import TrialAttempt, parse_trial_attempt
from aptl.core.trial_control import TrialControl
from aptl.core.trial_record import TRIAL_RECORD_RELPATH
from aptl.core.trial_sdl import DeclaredParticipant
from aptl.workbench.trial_run import run_declared_trial

_PARTICIPANTS = (
    DeclaredParticipant("red-operator", "red", "openrouter/vendor-a/model-a", ("red-task",)),
    DeclaredParticipant("blue-operator", "blue", "openrouter/vendor-b/model-b", ("blue-task",)),
)


class FinishingInvocation:
    prompt_sha256 = "a" * 64

    def __call__(self, action_id, cancellation):
        return "finished output"


class BlockingInvocation:
    """Write partial output, then wait for cancellation like a long model turn."""

    prompt_sha256 = "b" * 64

    def __init__(self):
        self.started = threading.Event()

    def __call__(self, action_id, cancellation):
        self.started.set()
        cancellation.wait(30)
        raise RuntimeError("participant invocation cancelled after partial output")


def _store(tmp_path, run_id):
    store = LocalRunStore(tmp_path / "runs")
    store.create_run(run_id)
    store.write_json(run_id, "manifest.json", {"startup": "synthetic"})
    return store


def _run(tmp_path, attempt, invocations, *, control=None, evidence=None):
    store = _store(tmp_path, attempt.run_id)
    try:
        record = run_declared_trial(
            attempt=attempt,
            scenario_sha256="sha256:" + "1" * 64,
            participants=_PARTICIPANTS,
            invocations=invocations,
            evidence=evidence or {},
            control=control or TrialControl(tmp_path / "state"),
            store=store,
            clock=lambda: datetime.now(UTC),
            poll_seconds=0.05,
        )
    except (RuntimeError, ValueError) as exc:
        pytest.fail(f"the trial did not run to a seal: {exc}")
    return store, record


def test_sealed_trial_run_uses_caller_run_and_attempt_ids(tmp_path, monkeypatch):
    deadline = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=5)
    try:
        attempt = parse_trial_attempt("R1", "A1", deadline.strftime("%Y-%m-%dT%H:%M:%SZ"))
    except ValueError as exc:
        pytest.fail(f"valid trial options were refused: {exc}")
    assert attempt == TrialAttempt("R1", "A1", deadline)

    store, record = _run(
        tmp_path,
        attempt,
        {item.address: FinishingInvocation() for item in _PARTICIPANTS},
    )

    sealed = verify_sealed_archive(store.base_dir, "R1")
    assert sealed is not None and sealed.run_id == "R1"
    assert TRIAL_RECORD_RELPATH in sealed.inventory_paths
    written = json.loads((store.get_run_path("R1") / TRIAL_RECORD_RELPATH).read_text())
    assert written["run_id"] == "R1" and written["attempt_id"] == "A1"
    assert record.terminal_cause == "completed"
    assert {item.status for item in record.participants} == {"completed"}

    for bad in (("R1", None, None), ("../escape", "A1", "2026-11-06T00:00:00Z"), ("R1", "A1", "tomorrow")):
        with pytest.raises(ValueError):
            parse_trial_attempt(*bad)

    from aptl.cli import lab as lab_cli

    started = []
    monkeypatch.setattr(lab_cli, "orchestrate_lab_start", lambda *a, **k: started.append(k))
    result = CliRunner().invoke(lab_cli.app, ["start", "--run-id", "R1"])
    assert result.exit_code == 2
    assert started == []


def test_trial_stops_at_deadline_or_stop_request_and_keeps_partial_evidence(tmp_path):
    for cause in ("deadline", "stopped"):
        _check_stop(tmp_path / cause, cause)


def _check_stop(tmp_path, cause):
    tmp_path.mkdir()
    now = datetime.now(UTC)
    deadline = now + (timedelta(seconds=1) if cause == "deadline" else timedelta(minutes=5))
    invocations = {item.address: BlockingInvocation() for item in _PARTICIPANTS}
    control = TrialControl(tmp_path / "state")
    evidence = {
        item.address: {"status": "running", "stdout_bytes": 17} for item in _PARTICIPANTS
    }
    if cause == "stopped":

        def request_stop():
            for invocation in invocations.values():
                invocation.started.wait(10)
            control.request_stop()

        threading.Thread(target=request_stop, daemon=True).start()

    store, record = _run(
        tmp_path,
        TrialAttempt("R2", "A2", deadline),
        invocations,
        control=control,
        evidence=evidence,
    )

    assert record.terminal_cause == cause
    assert {item.status for item in record.participants} == {"cancelled"}
    for item in record.participants:
        assert item.invocation == evidence[item.address]
        assert item.failure
    sealed = verify_sealed_archive(store.base_dir, "R2")
    assert sealed is not None
    assert TRIAL_RECORD_RELPATH in sealed.inventory_paths
    assert control.active() is None
    assert not any(Path(tmp_path / "state").rglob("*.json"))
