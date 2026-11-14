"""A trial seals under caller IDs and stops at its deadline or on request (#1670)."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta

import pytest
from typer.testing import CliRunner

from aptl.core.archival import verify_sealed_archive
from aptl.core.runstore import LocalRunStore
from aptl.core.trial_attempt import TrialAttempt, parse_trial_attempt
from aptl.core.trial_control import TrialControl
from aptl.core.trial_record import TRIAL_RECORD_RELPATH, seal_trial_record
from aptl.core.trial_sdl import DeclaredParticipant
from aptl.workbench.trial_run import DeclaredTrial, TrialSupervision
from tests.native_trial_runtime import run_native_trial as run_declared_trial

_PARTICIPANTS = (
    DeclaredParticipant(
        "red-operator", "red", "openrouter/vendor-a/model-a", ("red-task",)
    ),
    DeclaredParticipant(
        "blue-operator", "blue", "openrouter/vendor-b/model-b", ("blue-task",)
    ),
)


class FinishingInvocation:
    prompt_sha256 = "a" * 64

    def __call__(self, action_id, cancellation):
        return "finished output"


class PartialInvocation:
    """Report partial native evidence, then wait for cancellation like a long turn."""

    prompt_sha256 = "b" * 64

    def __init__(self, address, evidence):
        self.address, self.evidence = address, evidence
        self.started = threading.Event()

    def __call__(self, action_id, cancellation):
        # The real executor reports through its evidence sink while it runs.
        self.evidence[self.address] = {
            "action_id": action_id,
            "status": "running",
            "partial_text_sha256": "c" * 64,
            "output_tokens": 7,
        }
        self.started.set()
        cancellation.wait(30)
        self.evidence[self.address] = {
            **self.evidence[self.address],
            "status": "cancelled",
        }
        raise RuntimeError("participant invocation cancelled after partial output")


def _store(tmp_path, run_id):
    store = LocalRunStore(tmp_path / "runs")
    store.create_run(run_id)
    store.write_json(run_id, "manifest.json", {"startup": "synthetic"})
    return store


def _run(
    tmp_path, attempt, invocations, *, stop_requested=lambda: False, evidence=None
):
    store = _store(tmp_path, attempt.run_id)
    record = run_declared_trial(
        DeclaredTrial(attempt, "sha256:" + "1" * 64, _PARTICIPANTS),
        invocations=invocations,
        evidence=evidence if evidence is not None else {},
        store=store,
        supervision=TrialSupervision(
            stop_requested, lambda: datetime.now(UTC), poll_seconds=0.05
        ),
    )
    seal_trial_record(store, record)
    return store, record


def test_sealed_trial_run_uses_caller_run_and_attempt_ids(tmp_path, monkeypatch):
    deadline = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=5)
    attempt = parse_trial_attempt("R1", "A1", deadline.strftime("%Y-%m-%dT%H:%M:%SZ"))
    assert attempt == TrialAttempt("R1", "A1", deadline)

    store, record = _run(
        tmp_path,
        attempt,
        {item.address: FinishingInvocation() for item in _PARTICIPANTS},
    )

    sealed = verify_sealed_archive(store.base_dir, "R1")
    assert sealed is not None
    assert sealed.run_id == "R1"
    assert TRIAL_RECORD_RELPATH in sealed.inventory_paths
    written = json.loads((store.get_run_path("R1") / TRIAL_RECORD_RELPATH).read_text())
    assert written["run_id"] == "R1"
    assert written["attempt_id"] == "A1"
    assert record.terminal_cause == "completed"
    assert {item.status for item in record.participants} == {"completed"}

    for bad in (
        ("R1", None, None),
        ("../escape", "A1", "2026-11-06T00:00:00Z"),
        ("R1", "A1", "tomorrow"),
    ):
        with pytest.raises(ValueError):
            parse_trial_attempt(*bad)

    from aptl.cli import lab as lab_cli

    started = []
    monkeypatch.setattr(
        lab_cli, "orchestrate_lab_start", lambda *a, **k: started.append(k)
    )
    result = CliRunner().invoke(lab_cli.app, ["start", "--run-id", "R1"])
    assert result.exit_code == 2
    assert started == []


def test_trial_stops_at_deadline_or_stop_request_and_keeps_partial_evidence(tmp_path):
    for cause in ("deadline", "stopped"):
        _check_stop(tmp_path / cause, cause)


def _check_stop(tmp_path, cause):
    from aptl.core.lab import request_trial_stop

    tmp_path.mkdir()
    now = datetime.now(UTC)
    deadline = now + (
        timedelta(seconds=1) if cause == "deadline" else timedelta(minutes=5)
    )
    attempt = TrialAttempt("R2", "A2", deadline)
    evidence: dict[str, dict[str, object]] = {}
    invocations = {
        item.address: PartialInvocation(item.address, evidence)
        for item in _PARTICIPANTS
    }
    control = TrialControl(tmp_path)
    stop_results = []
    control.claim(attempt)
    control.begin(attempt)
    if cause == "stopped":

        def stop_through_lab():
            for invocation in invocations.values():
                invocation.started.wait(10)
            stop_results.append(request_trial_stop(tmp_path, wait_seconds=30))

        stopper = threading.Thread(target=stop_through_lab, daemon=True)
        stopper.start()

    store, record = _run(
        tmp_path,
        attempt,
        invocations,
        stop_requested=control.stop_requested,
        evidence=evidence,
    )
    control.release(attempt)
    if cause == "stopped":
        stopper.join(30)
        assert stop_results == [None]

    assert record.terminal_cause == cause
    assert {item.status for item in record.participants} == {"cancelled"}
    for item in record.participants:
        assert item.invocation["partial_text_sha256"] == "c" * 64
        assert item.invocation["status"] == "cancelled"
        assert item.failure
    sealed = verify_sealed_archive(store.base_dir, "R2")
    assert sealed is not None
    assert TRIAL_RECORD_RELPATH in sealed.inventory_paths
    assert control.active() is None


def test_seal_declares_raw_trial_captures_as_evidence_blobs(tmp_path):
    from aptl.core.trial_record import _run_files

    store = _store(tmp_path, "R2")
    for relative in (
        "trial/transcripts/agents.red.json",
        "trial/soc/wazuh.ndjson",
        "trial/audit/audit.log",
    ):
        store.write_file("R2", relative, b"{}")
    store.write_file("R2", "evidence/records/record.json", b"{}")
    specs = {
        spec.path: (spec.role, spec.media_type)
        for spec in _run_files(store.get_run_path("R2"))
    }
    assert specs["trial/transcripts/agents.red.json"] == (
        "evidence-blob",
        "application/json",
    )
    assert specs["trial/soc/wazuh.ndjson"] == ("evidence-blob", "application/x-ndjson")
    assert specs["trial/audit/audit.log"] == (
        "evidence-blob",
        "application/octet-stream",
    )
    assert specs["evidence/records/record.json"] == (
        "evidence-record",
        "application/json",
    )


def test_the_shared_episode_end_cancels_both_participants_and_completes_the_trial(
    tmp_path,
):
    """At the episode end both participants stop; that is the trial's normal end, not a failure."""
    attempt = TrialAttempt("R3", "A3", datetime.now(UTC) + timedelta(minutes=5))
    evidence: dict[str, dict[str, object]] = {}
    invocations = {
        item.address: PartialInvocation(item.address, evidence)
        for item in _PARTICIPANTS
    }
    record = run_declared_trial(
        DeclaredTrial(attempt, "sha256:" + "1" * 64, _PARTICIPANTS, episode_seconds=1),
        invocations=invocations,
        evidence=evidence,
        store=_store(tmp_path, attempt.run_id),
        supervision=TrialSupervision(
            lambda: False, lambda: datetime.now(UTC), poll_seconds=0.05
        ),
    )
    assert record.terminal_cause == "completed"
    assert {item.status for item in record.participants} == {"cancelled"}
    assert all(item.failure for item in record.participants)
