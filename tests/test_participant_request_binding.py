"""Trusted participant and SDL scope cannot come from reconstructed request data."""

from pathlib import Path
from dataclasses import replace
from threading import Event
from functools import partial
import json

import pytest

from aptl.workbench.agent import ClaudeCodeManagedAgentAdapter
from aptl.workbench.codex_agent import CodexManagedAgentAdapter
from aptl.workbench.process import AgentExecutionError
from aptl.workbench.runtime import DecisionAgentLaunch
from tests.test_participant_request_dispatch import prepared_request
from tests.opencode_fixture import synthetic_options
from aptl.core.participant_requests import ParticipantRequestBinding
from aptl.core.opencode import OpenRouterRoute
from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor


@pytest.mark.parametrize("provider", ["claude", "codex"])
def test_reconstructed_request_requires_independent_trusted_binding(tmp_path, provider):
    request = prepared_request(provider, Path("/bin/true"))
    factory = (
        ClaudeCodeManagedAgentAdapter
        if provider == "claude"
        else CodexManagedAgentAdapter
    )
    adapter = factory(
        **{f"{provider}_executable": Path("/bin/true")}, work_dir=tmp_path
    )
    launch = DecisionAgentLaunch(
        provider=provider, model=request.profile.model, run_id="scope", request=request
    )
    credentials = {
        "ANTHROPIC_API_KEY"
        if provider == "claude"
        else "CODEX_API_KEY": "fixture-local-only"
    }
    with pytest.raises(AgentExecutionError, match="binding"):
        adapter.launch(launch, credentials)


@pytest.mark.parametrize("provider", ["claude", "codex", "opencode"])
@pytest.mark.parametrize("scope_attack", [False, True])
@pytest.mark.parametrize("after_launch", [False, True])
def test_peer_or_incompatible_scope_never_reaches_dispatch(
    tmp_path, monkeypatch, provider, scope_attack, after_launch
):
    executable = Path("/bin/true")
    request, owner, scenario = prepared_request(provider, executable, with_owner=True)
    scenario.agents["peer"] = type(scenario.agents["operator"])(role="green")
    owner = owner.for_scenario(scenario)
    peer = request.configuration_result.model_dump(mode="json")
    peer["participant_address"] = "agents.peer"
    forged = replace(request, configuration_json=json.dumps(peer))
    assert forged.prompt == request.prompt
    assert forged.context_descriptors == request.context_descriptors
    forged.validate()  # Integrity alone cannot establish participant scope.
    binding = ParticipantRequestBinding(
        owner, "agents.peer" if scope_attack else "agents.operator"
    )

    class Runner:
        calls = 0

        def run(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("provider work must never start")

    runner = Runner()
    initial = request if after_launch else forged
    initial_binding = (
        ParticipantRequestBinding(owner, "agents.operator") if after_launch else binding
    )
    if provider == "opencode":
        options = replace(
            synthetic_options(
                executable=executable,
                work_root=tmp_path,
                runner=runner,
                request=initial,
                request_binding=initial_binding,
            ),
            route=OpenRouterRoute(
                endpoint=request.profile.gateway_endpoint,
                serving_provider=request.profile.serving_provider,
            ),
        )
        operation = partial(
            LilraeOpenCodeExecutor,
            options=options,
            model=initial.profile.model,
            prompt=initial.prompt,
            timeout_seconds=30,
            configuration_result=initial.configuration_result,
        )
        if after_launch:
            active = operation()
            monkeypatch.setattr(active, "_request", forged)
            monkeypatch.setattr(active, "_request_binding", binding)
            operation = partial(active, "scope-attack", Event())
        with pytest.raises((ValueError, AgentExecutionError)):
            operation()
    else:
        factory = (
            ClaudeCodeManagedAgentAdapter
            if provider == "claude"
            else CodexManagedAgentAdapter
        )
        adapter = factory(
            **{f"{provider}_executable": executable}, work_dir=tmp_path, runner=runner
        )
        launch = DecisionAgentLaunch(
            provider=provider,
            model=initial.profile.model,
            run_id="scope",
            request=initial,
            request_binding=initial_binding,
        )
        credentials = {
            "ANTHROPIC_API_KEY"
            if provider == "claude"
            else "CODEX_API_KEY": "private-fixture-key"
        }
        operation = partial(adapter.launch, launch, credentials)
        if after_launch:
            handle = operation()
            handle.launch = replace(
                handle.launch, request=forged, request_binding=binding
            )
            adapter.list_tools(handle)
            operation = partial(
                adapter.respond,
                handle,
                "choose",
                response_schema={
                    "type": "object",
                    "properties": {
                        "candidate": {"type": "integer", "minimum": 0, "maximum": 0}
                    },
                    "required": ["candidate"],
                    "additionalProperties": False,
                },
            )
        with pytest.raises(AgentExecutionError, match="binding"):
            operation()
    assert runner.calls == 0


def test_opencode_reconstruction_requires_independent_trusted_binding(tmp_path):
    executable = Path("/bin/true")
    request = prepared_request("opencode", executable)
    options = replace(
        synthetic_options(executable=executable, work_root=tmp_path),
        request=request,
        route=OpenRouterRoute(
            endpoint=request.profile.gateway_endpoint,
            serving_provider=request.profile.serving_provider,
        ),
    )
    with pytest.raises(ValueError, match="binding"):
        LilraeOpenCodeExecutor(
            options=options,
            model=request.profile.model,
            prompt=request.prompt,
            timeout_seconds=30,
            configuration_result=request.configuration_result,
        )
