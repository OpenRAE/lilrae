"""Managed build, route, and retained evidence at the OpenCode boundary."""

import hashlib
import json
from pathlib import Path
from threading import Event

import pytest

from aptl.workbench.process import AgentExecutionError, ProcessResult


def options(tmp_path, runner, *, evidence_sink=None):
    from aptl.core.opencode import OpenCodeBuild, OpenRouterRoute
    from aptl.workbench.lilrae_opencode import OpenCodeOptions

    executable = tmp_path / "fake-opencode"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o700)
    return OpenCodeOptions(
        executable=executable,
        work_root=tmp_path,
        build=OpenCodeBuild(
            version="1.19.5",
            executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        ),
        route=OpenRouterRoute(
            endpoint="https://openrouter.ai/api/v1", serving_provider="test-provider"
        ),
        environment={"OPENROUTER_API_KEY": "private-test-credential"},
        runner=runner,
        evidence_sink=evidence_sink,
    )


class Runner:
    def __init__(self, events):
        self.events = events
        self.calls = []

    def run(self, argv, **kwargs):
        config = json.loads(Path(kwargs["env"]["OPENCODE_CONFIG"]).read_text())
        self.calls.append((argv, kwargs, config))
        return ProcessResult(
            0, b"\n".join(json.dumps(e).encode() for e in self.events), b""
        )


def executor(settings):
    from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor

    return LilraeOpenCodeExecutor(
        options=settings,
        model="openrouter/test/model",
        prompt="private prompt",
        timeout_seconds=30,
    )


def test_changed_build_cannot_dispatch(tmp_path):
    runner = Runner([])
    settings = options(tmp_path, runner)
    active = executor(settings)
    settings.executable.write_text("#!/bin/sh\necho changed\n")
    cancellation = Event()
    with pytest.raises(AgentExecutionError, match="build"):
        active("action-1", cancellation)
    assert not runner.calls
    assert active.last_evidence.status == "failed"


def test_route_is_exclusive_and_credential_free(tmp_path):
    events = [
        {"type": "text", "part": {"text": "done"}},
        {
            "type": "step_finish",
            "part": {
                "reason": "stop",
                "tokens": {"input": 12, "output": 3},
                "cost": 0.01,
            },
        },
    ]
    runner = Runner(events)
    records = []
    active = executor(options(tmp_path, runner, evidence_sink=records.append))
    assert active("action-1", Event()) == "done"
    argv, kwargs, config = runner.calls[0]
    assert config["enabled_providers"] == ["openrouter"]
    provider = config["provider"]["openrouter"]
    assert provider["whitelist"] == ["test/model"]
    assert provider["options"]["baseURL"] == "https://openrouter.ai/api/v1"
    routing = provider["models"]["test/model"]["options"]["provider"]
    assert routing["only"] == ["test-provider"]
    assert routing["allow_fallbacks"] is False
    assert config["small_model"] == "openrouter/test/model"
    assert config["compaction"]["auto"] is False
    assert "private-test-credential" not in repr((argv, config, records))
    assert "private prompt" not in repr(records)
    assert records[0].status == "succeeded"
    assert records[0].input_tokens == 12
    assert records[0].served_model is None


@pytest.mark.parametrize(
    "events",
    [
        [{"type": "text", "part": {"text": "partial"}}],
        [
            {"type": "text", "part": {"text": "partial"}},
            {"type": "error", "error": {"message": "private-test-credential"}},
        ],
    ],
)
def test_partial_response_is_retained_without_claiming_success(tmp_path, events):
    records = []
    active = executor(options(tmp_path, Runner(events), evidence_sink=records.append))
    cancellation = Event()
    with pytest.raises(AgentExecutionError):
        active("action-1", cancellation)
    assert len(records) == 1
    assert records[0].status == "failed"
    assert records[0].stdout_bytes > 0
    if events[0]["type"] == "text":
        assert records[0].partial_text_sha256 == hashlib.sha256(b"partial").hexdigest()
    assert "private-test-credential" not in repr(records)


def test_a_model_output_limit_ends_the_participant_with_its_finish_reason(tmp_path):
    records = []
    events = [
        {
            "type": "step_finish",
            "part": {"reason": "length", "tokens": {"input": 12, "output": 3}},
        }
    ]
    active = executor(options(tmp_path, Runner(events), evidence_sink=records.append))
    assert active("action-1", Event()) == ""
    assert (records[0].status, records[0].finish_reason) == ("succeeded", "length")


def test_duplicate_json_event_cannot_become_completion():
    from aptl.workbench.opencode_events import _terminal_text

    with pytest.raises(AgentExecutionError):
        _terminal_text(
            b'{"type":"error","type":"text","part":{"text":"done"}}\n{"type":"step_finish","part":{"reason":"stop"}}'
        )


def test_unknown_json_event_cannot_become_completion():
    from aptl.workbench.opencode_events import _terminal_text

    with pytest.raises(AgentExecutionError):
        _terminal_text(
            b'{"type":"text","part":{"text":"done"}}\n{"type":"unknown"}\n{"type":"step_finish","part":{"reason":"stop"}}'
        )


def test_invalid_unicode_retains_safe_session_metadata():
    from aptl.workbench.opencode_events import parse_opencode_response

    response = parse_opencode_response(
        b'{"type":"text","sessionID":"ses_partial","part":{"text":"\\ud800"}}\n'
    )
    assert response.valid is False
    assert response.session_id == "ses_partial"
    assert response.partial_text_sha256 is None


def test_error_event_retains_session_without_provider_error_body():
    from aptl.workbench.opencode_events import parse_opencode_response

    response = parse_opencode_response(
        b'{"type":"error","sessionID":"ses_partial","error":{"message":"private-test-credential"}}\n'
    )
    assert response.valid is False
    assert response.session_id == "ses_partial"
    assert "private-test-credential" not in repr(response)


def test_oversized_cost_retains_safe_partial_evidence():
    from aptl.workbench.opencode_events import parse_opencode_response

    event = {
        "type": "step_finish",
        "sessionID": "ses_partial",
        "part": {"reason": "stop", "cost": 10**1000},
    }
    response = parse_opencode_response(json.dumps(event).encode())
    assert response.valid is False
    assert response.session_id == "ses_partial"
    assert response.cost is None


@pytest.mark.parametrize(
    "reason", ["error", "length", "content-filter", "other", "unknown"]
)
def test_terminal_failure_cannot_be_replaced_by_later_stop(tmp_path, reason):
    records = []
    events = [
        {"type": "text", "sessionID": "ses_partial", "part": {"text": "partial"}},
        {
            "type": "step_finish",
            "sessionID": "ses_partial",
            "part": {"reason": reason, "tokens": {"input": 12, "output": 3}},
        },
        {"type": "step_finish", "sessionID": "ses_partial", "part": {"reason": "stop"}},
    ]
    active = executor(options(tmp_path, Runner(events), evidence_sink=records.append))
    cancellation = Event()
    with pytest.raises(AgentExecutionError):
        active("action-1", cancellation)
    assert records[0].status == "failed"
    assert records[0].finish_reason == reason
    assert records[0].session_id == "ses_partial"
    assert records[0].input_tokens == 12
    assert records[0].partial_text_sha256 == hashlib.sha256(b"partial").hexdigest()


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://user:secret@openrouter.ai/api/v1",
        "https://openrouter.ai/api/v1?key=secret",
        "https://evil.example/api/v1",
        "http://openrouter.ai/api/v1",
    ],
)
def test_route_rejects_unapproved_or_credential_bearing_destinations(endpoint):
    from aptl.core.opencode import OpenRouterRoute

    with pytest.raises(ValueError):
        OpenRouterRoute(endpoint=endpoint, serving_provider="test-provider")


def test_installed_opencode_selection_and_source_are_projected_without_locator():
    from aptl.core.config import AptlConfig
    from aptl.core.provenance.providers.config_identity import safe_config_projection

    config = AptlConfig.model_validate(
        {
            "lab": {"name": "test-1504"},
            "experiment": {
                "participant_models": {"opencode": "openrouter/test/model"},
                "participant_credential_sources": {
                    "opencode": {
                        "kind": "process-environment",
                        "variable": "PRIVATE_SOURCE_NAME",
                    }
                },
            },
        }
    )
    assert (
        config.experiment.participant_models.model_for("opencode")
        == "openrouter/test/model"
    )
    assert (
        config.experiment.participant_credential_sources.source_for("opencode").variable
        == "PRIVATE_SOURCE_NAME"
    )
    projection = safe_config_projection(config)
    assert "openrouter/test/model" in repr(projection)
    assert "PRIVATE_SOURCE_NAME" not in repr(projection)
    assert "opencode" in repr(projection)


def test_managed_source_is_minimal_and_cleaned_after_use(tmp_path):
    from aptl.core.config import ProcessEnvironmentCredentialSource
    from aptl.workbench.opencode_bootstrap import (
        OpenCodeParticipantRequest,
        managed_opencode_executor,
    )
    from tests.opencode_fixture import synthetic_options
    from tests.test_lilrae_participant_configuration import configuration
    from tests.test_lilrae_opencode import RecordingRunner

    manifest, result = configuration()
    runner = RecordingRunner()
    settings = synthetic_options(
        executable=Path("/bin/true"), work_root=tmp_path, runner=runner
    )
    with managed_opencode_executor(
        options=settings,
        request=OpenCodeParticipantRequest(
            configuration=result,
            manifest=manifest,
            prompt="red task",
            prompt_ref="content.red-prompt@v1",
            supported_models=frozenset({"openrouter/model"}),
        ),
        run_id="trial-red",
        credential_source=ProcessEnvironmentCredentialSource(
            kind="process-environment", variable="PRIVATE_SOURCE"
        ),
        source_environment={
            "PRIVATE_SOURCE": "private-test-credential",
            "UNRELATED": "never-forward",
        },
    ) as (active, evidence):
        assert active("action-1", Event()) == "done"
        assert "UNRELATED" not in runner.calls[0][1]["env"]
        assert evidence.acquisition == "succeeded"
    assert evidence.local_cleanup == "succeeded"
    assert "private-test-credential" not in repr(evidence.to_payload())
    cancellation = Event()
    with pytest.raises(AgentExecutionError, match="closed"):
        active("action-2", cancellation)


def test_private_context_cleanup_failure_cannot_record_success(tmp_path, monkeypatch):
    from contextlib import contextmanager
    import aptl.workbench.lilrae_opencode as implementation

    real_directory = implementation.TemporaryDirectory

    @contextmanager
    def failing_cleanup(**kwargs):
        with real_directory(**kwargs) as directory:
            yield directory
        raise OSError("private-test-credential")

    monkeypatch.setattr(implementation, "TemporaryDirectory", failing_cleanup)
    runner = Runner(
        [
            {"type": "text", "part": {"text": "done"}},
            {"type": "step_finish", "part": {"reason": "stop"}},
        ]
    )
    records = []
    active = executor(options(tmp_path, runner, evidence_sink=records.append))
    cancellation = Event()
    with pytest.raises(AgentExecutionError) as error:
        active("action-1", cancellation)
    assert "private-test-credential" not in str(error.value)
    assert len(records) == 1
    assert records[0].status == "failed"
    assert records[0].partial_text_sha256 == hashlib.sha256(b"done").hexdigest()


def test_timeout_retains_commitment_to_partial_response(tmp_path):
    from dataclasses import replace
    import sys
    from aptl.core.opencode import OpenCodeBuild
    from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor
    from aptl.workbench.process import BoundedProcessError

    settings = options(tmp_path, None)
    partial = (
        b'{"type":"step_start","sessionID":"ses_partial"}\n'
        b'{"type":"text","sessionID":"ses_partial","part":{"text":"partial"}}\n'
        b'{"type":"step_finish","sessionID":"ses_partial","part":{"reason":"tool-calls","tokens":{"input":12,"output":3},"cost":0.01}}\n'
    )
    settings.executable.write_text(
        f"#!{sys.executable}\nimport sys,time\nsys.stdout.buffer.write({partial!r})\nsys.stdout.flush()\ntime.sleep(60)\n"
    )
    settings = replace(
        settings,
        build=OpenCodeBuild(
            version="1.19.5",
            executable_sha256=hashlib.sha256(
                settings.executable.read_bytes()
            ).hexdigest(),
        ),
    )
    active = LilraeOpenCodeExecutor(
        options=settings,
        model="openrouter/test/model",
        prompt="task",
        timeout_seconds=0.5,
    )
    cancellation = Event()
    with pytest.raises(BoundedProcessError):
        active("timed-action", cancellation)
    assert active.last_evidence.status == "failed"
    assert active.last_evidence.stdout_sha256 == hashlib.sha256(partial).hexdigest()
    assert active.last_evidence.cleanup_residual == ()
    assert active.last_evidence.session_id == "ses_partial"
    assert active.last_evidence.input_tokens == 12
    assert active.last_evidence.output_tokens == 3
    assert (
        active.last_evidence.partial_text_sha256
        == hashlib.sha256(b"partial").hexdigest()
    )


def test_evidence_sink_failure_is_safe_and_cannot_claim_success(tmp_path):
    def unavailable_sink(record):
        raise RuntimeError("private-test-credential")

    runner = Runner(
        [
            {"type": "text", "part": {"text": "done"}},
            {"type": "step_finish", "part": {"reason": "stop"}},
        ]
    )
    active = executor(options(tmp_path, runner, evidence_sink=unavailable_sink))
    cancellation = Event()
    with pytest.raises(AgentExecutionError) as error:
        active("action-1", cancellation)
    assert "private-test-credential" not in str(error.value)
    assert active.last_evidence.status == "failed"


@pytest.mark.parametrize("limit", [0, -1, True, 32769, 1.5])
def test_invalid_request_token_cap_fails_before_dispatch(tmp_path, limit):
    from dataclasses import replace

    runner = Runner([])
    settings = replace(options(tmp_path, runner), max_output_tokens=limit)
    with pytest.raises(ValueError, match="limits"):
        executor(settings)
    assert not runner.calls


@pytest.mark.parametrize(
    "model",
    [
        "auto",
        "openrouter/model --plugin untrusted",
        "openrouter/model\nother",
        "anthropic/other",
    ],
)
def test_project_model_selection_rejects_unsafe_or_unselected_provider(model):
    from aptl.core.config import InstalledParticipantModels

    with pytest.raises(ValueError):
        InstalledParticipantModels(opencode=model)
