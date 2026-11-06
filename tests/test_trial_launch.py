"""Vertex AI participants use a referenced key that no trial artifact retains (#1670)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from aptl.core.config import ExperimentSettings
from aptl.core.opencode import OpenCodeBuild
from aptl.core.runstore import LocalRunStore
from aptl.core.trial_attempt import TrialAttempt
from aptl.core.trial_control import TrialControl
from aptl.core.trial_sdl import declared_participants
from aptl.workbench.process import ProcessResult
from aptl.workbench.trial_launch import TrialLaunchSettings, trial_executors
from aptl.workbench.trial_run import run_declared_trial
from tests.trial_sdl_fixture import parse_trial, read_fixture_asset, trial_document

_PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\nsynthetic-vertex-key-material\n-----END PRIVATE KEY-----\n"
_KEY_JSON = json.dumps(
    {
        "type": "service_account",
        "project_id": "synthetic-project",
        "private_key": _PRIVATE_KEY,
        "client_email": "participant@synthetic-project.iam.gserviceaccount.com",
    }
)


class KeyReadingRunner:
    """Record what each child would receive, including its key file bytes."""

    def __init__(self):
        self.calls = []

    def run(self, argv, **options):
        env = options["env"]
        key_path = env.get("GOOGLE_APPLICATION_CREDENTIALS")
        self.calls.append(
            {
                "argv": argv,
                "env": dict(env),
                "config": json.loads(Path(env["OPENCODE_CONFIG"]).read_text()),
                "key": Path(key_path).read_text() if key_path else None,
                "key_path": key_path,
            }
        )
        return ProcessResult(
            0,
            b'{"type":"text","part":{"text":"done"}}\n{"type":"step_finish","part":{"reason":"stop"}}\n',
            b"",
        )


def _settings(tmp_path, runner, *, with_source=True):
    executable = tmp_path / "opencode"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o700)
    sources = (
        {"vertex": {"kind": "process-environment", "variable": "TEST_VERTEX_KEY"}}
        if with_source
        else {}
    )
    work = tmp_path / "work"
    work.mkdir(mode=0o700)
    return TrialLaunchSettings(
        executable=executable,
        work_root=work,
        experiment=ExperimentSettings.model_validate(
            {
                "participant_credential_sources": sources,
                "participant_serving_providers": {"openrouter/vendor-a/model-a": "vendor-a"},
            }
        ),
        source_environment={"TEST_VERTEX_KEY": _KEY_JSON, "OPENROUTER_TEST": "unused"},
        build=OpenCodeBuild(
            version="1.19.5",
            executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        ),
        runner=runner,
    )


def test_vertex_participant_key_comes_from_reference_and_stays_out_of_evidence(tmp_path):
    document = trial_document(
        red_model="google-vertex/vendor-d/model-d", blue_model="google-vertex/vendor-e/model-e"
    )
    scenario = parse_trial(document)
    participants = declared_participants(scenario)
    runner = KeyReadingRunner()
    settings = _settings(tmp_path, runner)
    deadline = datetime.now(UTC) + timedelta(minutes=5)
    store = LocalRunStore(tmp_path / "runs")
    store.create_run("run-1")
    store.write_json("run-1", "manifest.json", {"startup": "synthetic"})
    evidence: dict[str, dict[str, object]] = {}

    try:
        record = _run_vertex_trial(scenario, participants, settings, deadline, store, evidence, tmp_path)
    except (RuntimeError, ValueError) as exc:
        pytest.fail(f"the Vertex trial did not run to a seal: {exc}")
    _assert_vertex_trial(runner, record, document, participants, store)
    _assert_unconfigured_vertex_refused(tmp_path, scenario, participants, deadline)


def _run_vertex_trial(scenario, participants, settings, deadline, store, evidence, tmp_path):
    with trial_executors(
        scenario,
        participants,
        run_id="run-1",
        deadline=deadline,
        settings=settings,
        read_asset=read_fixture_asset,
        evidence_sink=lambda address, item: evidence.setdefault(address, {}).update(
            {"status": item.status}
        ),
    ) as executors:
        record = run_declared_trial(
            attempt=TrialAttempt("run-1", "attempt-1", deadline),
            scenario_sha256="sha256:" + "0" * 64,
            participants=participants,
            invocations=executors,
            evidence=evidence,
            control=TrialControl(tmp_path / "state"),
            store=store,
            clock=lambda: datetime.now(UTC),
        )
    return record


def _assert_vertex_trial(runner, record, document, participants, store):
    key_paths = [call["key_path"] for call in runner.calls]
    assert record.terminal_cause == "completed"
    assert len(runner.calls) == 2
    for call in runner.calls:
        assert call["key"] == _KEY_JSON
        assert call["env"]["GOOGLE_CLOUD_PROJECT"] == "synthetic-project"
        assert call["env"]["METADATA_SERVER_DETECTION"] == "none"
        assert call["config"]["enabled_providers"] == ["google-vertex"]
        assert "TEST_VERTEX_KEY" not in call["env"]
        assert _PRIVATE_KEY not in json.dumps(call["config"])
        assert _PRIVATE_KEY not in " ".join(call["argv"])
    assert all(path and not Path(path).exists() for path in key_paths)

    assert _PRIVATE_KEY not in json.dumps(document)
    for item in participants:
        assert "synthetic-vertex-key-material" not in item.model
    run_dir = store.get_run_path("run-1")
    for path in run_dir.rglob("*"):
        if path.is_file():
            assert b"synthetic-vertex-key-material" not in path.read_bytes(), path



def _assert_unconfigured_vertex_refused(tmp_path, scenario, participants, deadline):
    missing = tmp_path / "missing"
    missing.mkdir()
    unconfigured = _settings(missing, KeyReadingRunner(), with_source=False)
    with pytest.raises(ValueError):
        with trial_executors(
            scenario,
            participants,
            run_id="run-2",
            deadline=deadline,
            settings=unconfigured,
            read_asset=read_fixture_asset,
            evidence_sink=lambda address, item: None,
        ):
            pass
