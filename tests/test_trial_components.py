"""Focused failure paths of the lab-start trial components (#1670)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from threading import Event
from types import SimpleNamespace

import pytest

from aptl.core.lab_types import LabResult, StartupOutcome
from aptl.core.opencode import OpenRouterRoute, VertexRoute
from aptl.core.trial_attempt import TrialAttempt, parse_trial_attempt
from aptl.core.trial_control import TrialControl, trial_owner
from aptl.core.lifecycle_errors import LifecycleBusyError
from aptl.core.trial_ownership import TRIAL_FENCE
from aptl.workbench.opencode_configuration import (
    render_opencode_config,
    validate_provider_environment,
)
from aptl.workbench.trial_launch import _key_project, _provider, participant_tool_servers

_ATTEMPT = TrialAttempt("run-1", "attempt-1", datetime(2030, 1, 1, tzinfo=UTC))


def test_attempt_refuses_unsafe_ids_and_non_utc_deadlines():
    assert parse_trial_attempt(None, None, None) is None
    with pytest.raises(ValueError):
        TrialAttempt("run..1", "a", _ATTEMPT.deadline)
    not_utc = datetime(2030, 1, 1, tzinfo=timezone(timedelta(hours=1)))
    with pytest.raises(ValueError):
        TrialAttempt("r", "a", not_utc)
    with pytest.raises(ValueError):
        parse_trial_attempt("r", "a", "2030-01-01T00:00:00+01:00")
    parsed = parse_trial_attempt("r", "a", "2030-01-01T00:00:00.5Z")
    assert parsed.deadline.microsecond == 500000


def test_fence_blocks_a_second_attempt_and_releases_only_its_own(tmp_path):
    control = TrialControl(tmp_path)
    control.claim(_ATTEMPT)
    assert (tmp_path / TRIAL_FENCE).read_bytes() == trial_owner(_ATTEMPT)
    other = TrialAttempt("run-2", "attempt-1", _ATTEMPT.deadline)
    with pytest.raises(LifecycleBusyError):
        control.claim(other)
    with pytest.raises(RuntimeError):
        control.release(other)
    assert control.active().pid is None
    assert not control.runner_alive()
    assert control.request_stop().run_id == "run-1"
    assert control.request_stop().run_id == "run-1"
    assert control.stop_requested()
    control.release(_ATTEMPT)
    assert control.active() is None
    assert not control.stop_requested()
    assert control.request_stop() is None


def test_stop_releases_a_fence_whose_runner_is_gone(tmp_path):
    from aptl.core.lab import request_trial_stop

    control = TrialControl(tmp_path)
    control.claim(_ATTEMPT)
    gone = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                          capture_output=True, text=True, check=True)
    (tmp_path / ".aptl/trial/runner.json").write_text(json.dumps({"pid": int(gone.stdout)}))
    assert request_trial_stop(tmp_path, wait_seconds=5) is None
    assert control.active() is None
    assert not (tmp_path / TRIAL_FENCE).exists()


def test_stop_reports_a_live_runner_that_does_not_seal(tmp_path):
    from aptl.core.lab import request_trial_stop

    control = TrialControl(tmp_path)
    control.claim(_ATTEMPT)
    control.begin(_ATTEMPT)
    result = request_trial_stop(tmp_path, wait_seconds=0)
    assert result is not None
    assert not result.success
    assert control.stop_requested()
    assert request_trial_stop(tmp_path / "empty", wait_seconds=0) is None


def _start_context(tmp_path, trial):
    sdl = tmp_path / "trial.sdl.yaml"
    sdl.write_text("name: trial\n")
    return SimpleNamespace(
        trial=trial,
        start_selection=SimpleNamespace(bundle=SimpleNamespace(sdl_path=sdl)),
        run_id=trial.run_id if trial else None,
        project_dir=tmp_path,
    )


def test_start_binding_fences_only_a_usable_trial_start(tmp_path):
    from aptl.core.lab import _bind_trial_start

    ready = LabResult(success=True)
    assert _bind_trial_start(_start_context(tmp_path, None), ready).run_id is None
    unusable = LabResult(success=True, outcome=StartupOutcome.DEGRADED_UNUSABLE)
    assert _bind_trial_start(_start_context(tmp_path, _ATTEMPT), unusable).run_id is None
    assert not (tmp_path / TRIAL_FENCE).exists()

    bound = _bind_trial_start(_start_context(tmp_path, _ATTEMPT), LabResult(success=True))
    assert bound.run_id == "run-1"
    assert bound.scenario_sha256.startswith("sha256:")
    assert (tmp_path / TRIAL_FENCE).exists()

    (tmp_path / "other").mkdir()
    mismatch = _start_context(tmp_path / "other", _ATTEMPT)
    mismatch.run_id = "different"
    refused = _bind_trial_start(mismatch, LabResult(success=True))
    assert not refused.success
    assert refused.outcome is StartupOutcome.FAILED


def test_finalize_reports_no_pending_transcripts(tmp_path):
    from aptl.core.lab import finalize_trial_capture

    assert finalize_trial_capture(tmp_path) == "not-required"


def test_routes_admit_only_their_own_models_and_environment():
    vertex = VertexRoute("synthetic-project")
    router = OpenRouterRoute(endpoint="https://openrouter.ai/api/v1", serving_provider="z-ai")
    assert vertex.admits("google-vertex/zai-org/glm")
    assert not vertex.admits("openrouter/a/b")
    assert router.admits("openrouter/a/b")
    assert not router.admits("google-vertex/a")
    with pytest.raises(ValueError):
        VertexRoute("Not A Project")
    config = render_opencode_config("google-vertex/zai-org/glm", vertex, {"*": "deny"}, {})
    assert config["enabled_providers"] == ["google-vertex"]
    assert config["provider"]["google-vertex"] == {
        "whitelist": ["zai-org/glm"],
        "options": {"project": "synthetic-project", "location": "global"},
        "models": {"zai-org/glm": {}},
    }
    profile = SimpleNamespace()
    with pytest.raises(ValueError):
        render_opencode_config("google-vertex/a", vertex, {}, {}, request_profile=profile)
    validate_provider_environment({"GOOGLE_CLOUD_PROJECT": "p"}, vertex)
    with pytest.raises(ValueError):
        validate_provider_environment({"GOOGLE_CLOUD_PROJECT": "p"}, router)
    with pytest.raises(ValueError):
        validate_provider_environment({"GOOGLE_CLOUD_PROJECT": "p"})


@pytest.mark.parametrize(
    "key",
    ["not json", "[]", json.dumps({"type": "user", "project_id": "synthetic-project"}),
     json.dumps({"type": "service_account", "project_id": "X"})],
)
def test_vertex_key_must_be_a_service_account_key(key):
    with pytest.raises(ValueError) as caught:
        _key_project(key)
    assert key not in str(caught.value)


def test_unknown_model_provider_and_role_are_refused():
    no_settings = SimpleNamespace()
    with pytest.raises(ValueError):
        _provider("anthropic/claude", no_settings, None, "run-1")
    with pytest.raises(ValueError):
        participant_tool_servers("white", ("aptl-red",))
    settings = SimpleNamespace(experiment=SimpleNamespace(participant_serving_providers={}))
    unapproved = _provider("openrouter/a/b", settings, None, "run-1")
    with pytest.raises(ValueError):
        unapproved.__enter__()


def test_executor_requires_a_session_for_tools_unless_allowlisted(tmp_path):
    import hashlib

    from aptl.core.opencode import OpenCodeBuild
    from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor, OpenCodeOptions
    from aptl.workbench.process import AgentExecutionError

    executable = tmp_path / "opencode"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o700)
    options = OpenCodeOptions(
        executable=executable,
        work_root=tmp_path / "work",
        environment={"GOOGLE_CLOUD_PROJECT": "synthetic-project"},
        route=VertexRoute("synthetic-project"),
        build=OpenCodeBuild("1.19.5", hashlib.sha256(executable.read_bytes()).hexdigest()),
    )
    with pytest.raises(ValueError, match="route that admits the model"):
        LilraeOpenCodeExecutor(options=options, model="openrouter/a/b", prompt="p", timeout_seconds=5)
    executor = LilraeOpenCodeExecutor(
        options=options, model="google-vertex/a/b", prompt="p", timeout_seconds=5
    )
    executor._tool_servers = {"aptl-red": {}}
    cancellation = Event()
    with pytest.raises(AgentExecutionError, match="tool session"):
        executor("action", cancellation)
