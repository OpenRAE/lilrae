"""Published configurations reach existing native provider dispatch boundaries."""

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest
from raes_contracts.participant_control_context import control_context_asset_reference

from tests.participant_request_fixture import owner_fixture, realize
from tests.opencode_fixture import synthetic_options
from aptl.core.participant_requests import ParticipantRequestBinding


def prepared_request(
    provider,
    executable,
    *,
    endpoint=None,
    model=None,
    build_version=None,
    reasoning_mode="effort",
    reasoning_effort="high",
    top_p=None,
    with_owner=False,
):
    owner, scenario = owner_fixture(provider)
    payload = b"exact author prefix\n"
    asset = scenario.control_context_assets["brief-terse"]
    asset.content.checksum.value = hashlib.sha256(payload).hexdigest()
    asset.content.size_bytes = len(payload)
    profile = owner.catalog.profiles[0]
    changes = {
        "reasoning_mode": reasoning_mode,
        "reasoning_effort": {
            "state": "set" if reasoning_mode == "effort" else "omit",
            "value": reasoning_effort if reasoning_mode == "effort" else None,
        },
        "reasoning_budget": {
            "state": "set" if reasoning_mode == "budget" else "omit",
            "value": (32 if provider == "opencode" else 2048)
            if reasoning_mode == "budget"
            else None,
        },
    }
    # Revalidate the public JSON profile schema after changing reviewed fields.
    profile_data = {**profile.model_dump(mode="json"), **changes}
    if model is not None:
        profile_data["model"] = model
    if endpoint is not None:
        profile_data["gateway_endpoint"] = endpoint
    if provider == "opencode":
        profile_data.update(
            temperature={"state": "set", "value": 0.2},
            limit_scope="combined-generation",
            top_p={"state": "set" if top_p is not None else "omit", "value": top_p},
        )
    from aptl.core.participant_requests import RequestCatalog, ParticipantRequestOwner

    data = owner.catalog.model_dump(mode="json")
    data.update(
        executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        profiles=[profile_data],
    )
    if build_version is not None:
        data["build_version"] = build_version
    catalog = RequestCatalog.model_validate_json(json.dumps(data))
    owner = ParticipantRequestOwner(
        catalog=catalog,
        scenario=scenario,
        context_domains={
            "brief": {
                "control_context_assets.brief-terse": control_context_asset_reference(
                    asset
                )
            }
        },
    )
    request = owner.prepare_request(
        realize(owner),
        participant_address="agents.operator",
        contents={"brief": payload},
    )
    return (request, owner, scenario) if with_owner else request


def test_managed_opencode_accepts_its_published_configuration_at_dispatch(tmp_path):
    from aptl.core.opencode import OpenRouterRoute
    from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor
    from tests.test_opencode_managed import Runner

    executable = Path("/bin/true")
    request, owner, _ = prepared_request("opencode", executable, with_owner=True)
    runner = Runner(
        [
            {"type": "text", "part": {"text": "done"}},
            {"type": "step_finish", "part": {"reason": "stop"}},
        ]
    )
    settings = replace(
        synthetic_options(executable=executable, work_root=tmp_path, runner=runner),
        request=request,
        request_binding=ParticipantRequestBinding(owner, "agents.operator"),
        route=OpenRouterRoute(
            endpoint=request.profile.gateway_endpoint,
            serving_provider=request.profile.serving_provider,
        ),
    )
    active = LilraeOpenCodeExecutor(
        options=settings,
        model=request.profile.model,
        prompt=request.prompt,
        timeout_seconds=30,
        configuration_result=request.configuration_result,
    )
    assert active("action", Event()) == "done"
    _, launch, config = runner.calls[0]
    assert launch["stdin"] == b"exact author prefix\n"
    options = config["provider"]["openrouter"]["models"][
        request.profile.model.removeprefix("openrouter/")
    ]["options"]
    assert options["reasoning"] == {"effort": "high"}
    assert options["provider"]["allow_fallbacks"] is False
    assert config["agent"]["build"]["temperature"] == 0.2
    assert "top_p" not in config["agent"]["build"]


def test_configured_opencode_factory_accepts_the_published_request(tmp_path):
    from aptl.backends.lilrae_participant_configuration import (
        configured_opencode_executor,
    )
    from aptl.core.opencode import OpenRouterRoute
    from tests.test_opencode_managed import Runner

    executable = Path("/bin/true")
    request, owner, _ = prepared_request("opencode", executable, with_owner=True)
    runner = Runner(
        [
            {"type": "text", "part": {"text": "done"}},
            {"type": "step_finish", "part": {"reason": "stop"}},
        ]
    )
    options = replace(
        synthetic_options(executable=executable, work_root=tmp_path, runner=runner),
        request=request,
        request_binding=ParticipantRequestBinding(owner, "agents.operator"),
        route=OpenRouterRoute(
            endpoint=request.profile.gateway_endpoint,
            serving_provider=request.profile.serving_provider,
        ),
    )
    active = configured_opencode_executor(
        configuration=request.configuration_result,
        manifest=request.manifest,
        prompt=request.prompt,
        prompt_ref=request.prompt_ref,
        supported_models=frozenset({request.profile.model}),
        options=options,
        timeout_seconds=30,
    )
    assert active("action", Event()) == "done"
    assert runner.calls[0][1]["stdin"] == request.prompt.encode()


@pytest.mark.parametrize(
    "replace_contents,replace_descriptor", [(False, False), (True, False), (True, True)]
)
def test_reconstructed_request_cannot_replace_prompt_and_its_hash(
    replace_contents, replace_descriptor
):
    request = prepared_request("opencode", Path("/bin/true"))
    changed = "different private prompt\n"
    changes = {}
    if replace_contents:
        changes["context_contents"] = (changed,)
    if replace_descriptor:
        descriptor = json.loads(request.context_descriptors[0])
        descriptor["content"]["size_bytes"] = len(changed.encode())
        descriptor["content"]["checksum"]["value"] = hashlib.sha256(
            changed.encode()
        ).hexdigest()
        changes["context_descriptors"] = (json.dumps(descriptor),)
    changed_sha256 = hashlib.sha256(changed.encode()).hexdigest()
    with pytest.raises(ValueError, match="content"):
        replace(
            request,
            prompt=changed,
            prompt_sha256=changed_sha256,
            **changes,
        )


@pytest.mark.parametrize("provider", ["claude", "codex"])
def test_decision_adapters_apply_published_profile_and_prefix(tmp_path, provider):
    from aptl.workbench.agent import ClaudeCodeManagedAgentAdapter
    from aptl.workbench.codex_agent import CodexManagedAgentAdapter
    from aptl.workbench.runtime import DecisionAgentLaunch
    from aptl.workbench.process import ProcessResult

    executable = tmp_path / "cli"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o700)
    request, owner, _ = prepared_request(provider, executable, with_owner=True)
    calls = []

    class Runner:
        def run(self, argv, **kwargs):
            calls.append((argv, kwargs))
            content = (
                {"type": "result", "is_error": False, "result": '{"candidate":0}'}
                if provider == "claude"
                else {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": '{"candidate":0}'},
                }
            )
            return ProcessResult(0, json.dumps(content).encode(), b"")

    factory = (
        ClaudeCodeManagedAgentAdapter
        if provider == "claude"
        else CodexManagedAgentAdapter
    )
    kwargs = {
        (
            "claude_executable" if provider == "claude" else "codex_executable"
        ): executable
    }
    adapter = factory(**kwargs, work_dir=tmp_path / "work", runner=Runner())
    credential = "ANTHROPIC_API_KEY" if provider == "claude" else "CODEX_API_KEY"
    handle = adapter.launch(
        DecisionAgentLaunch(
            provider=provider,
            run_id="trial",
            model=request.profile.model,
            request=request,
            request_binding=ParticipantRequestBinding(owner, "agents.operator"),
        ),
        {credential: "private-fixture-key"},
    )
    adapter.list_tools(handle)
    assert "minimal-child-environment" in adapter.credential_isolation_controls(handle)
    schema = {
        "type": "object",
        "properties": {"candidate": {"type": "integer", "minimum": 0, "maximum": 0}},
        "required": ["candidate"],
        "additionalProperties": False,
    }
    assert (
        adapter.respond(handle, "decision body", response_schema=schema)
        == '{"candidate":0}'
    )
    argv, launch = calls[0]
    assert launch["stdin"] == b"exact author prefix\ndecision body"
    assert request.profile.model in argv
    assert "private-fixture-key" not in repr(argv)
    if provider == "claude":
        assert argv[argv.index("--effort") + 1] == "high"
        settings = json.loads(argv[argv.index("--settings") + 1])
        assert settings["availableModels"] == [request.profile.model]
        assert settings["fallbackModel"] == []
    else:
        assert 'model_reasoning_effort="high"' in argv
        assert 'model_provider="lilrae-openai"' in argv
    from aptl.workbench.process import AgentExecutionError

    executable.write_text("#!/bin/sh\necho replaced\n")
    with pytest.raises(AgentExecutionError, match="pin"):
        adapter.respond(handle, "second decision", response_schema=schema)
    assert len(calls) == 1
    adapter.close(handle)


@pytest.mark.integration
@pytest.mark.parametrize(
    "status,mode,effort",
    [
        (200, "effort", effort)
        for effort in ("none", "minimal", "low", "medium", "high", "xhigh")
    ]
    + [(401, "effort", "high"), (200, "disabled", None), (200, "budget", None)],
)
def test_real_opencode_transmits_published_controls_and_prompt(
    tmp_path, opencode_binary, status, mode, effort
):
    from tests.test_opencode_transport import provider
    from tests.opencode_fixture import install_wheel

    installed = install_wheel(tmp_path)
    with provider(status=status) as (endpoint, observations):
        request, owner, scenario = prepared_request(
            "opencode",
            opencode_binary,
            endpoint=endpoint,
            reasoning_mode=mode,
            reasoning_effort=effort,
            top_p=0.9 if mode == "budget" else None,
            with_owner=True,
        )
        payload = {
            **request.__dict__,
            "profile": request.profile.model_dump(mode="json"),
            "trusted": {
                "catalog": owner.catalog.model_dump(mode="json"),
                "scenario": scenario.model_dump(mode="json"),
            },
        }
        script = """
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from aptl.core.participant_requests import ParticipantRequest, RequestProfile,ParticipantRequestBinding,ParticipantRequestOwner,RequestCatalog
from raes import Scenario
from raes_contracts.participant_control_context import control_context_asset_reference
from aptl.core.opencode import OpenRouterRoute
from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor,OpenCodeOptions
import aptl
assert Path(aptl.__file__).is_relative_to(Path(sys.argv[1]))
data=json.loads(sys.stdin.read())
trusted=data.pop('trusted')
scenario=Scenario.model_validate(trusted['scenario'])
owner=ParticipantRequestOwner(catalog=RequestCatalog.model_validate_json(json.dumps(trusted['catalog'])),scenario=scenario,context_domains={'brief':{'control_context_assets.brief-terse':control_context_asset_reference(scenario.control_context_assets['brief-terse'])}})
data['profile']=RequestProfile.model_validate_json(json.dumps(data['profile']))
request=ParticipantRequest(**data)
options=OpenCodeOptions(executable=Path(sys.argv[2]),work_root=Path(sys.argv[3]),request_observation_required=True,request=request,request_binding=ParticipantRequestBinding(owner,'agents.operator'),environment={'OPENROUTER_API_KEY':'private-fixture-key'},route=OpenRouterRoute(endpoint=request.profile.gateway_endpoint,serving_provider=request.profile.serving_provider))
from threading import Event
active=LilraeOpenCodeExecutor(options=options,model=request.profile.model,prompt=request.prompt,timeout_seconds=90,configuration_result=request.configuration_result)
from aptl.workbench.process import AgentExecutionError
if sys.argv[4] == '200':
    assert active('action',Event()) == 'transport completion'
    assert active.last_evidence.input_tokens == 12
else:
    try:
        active('action',Event())
        raise AssertionError('provider rejection was accepted')
    except AgentExecutionError as exc:
        assert 'private-fixture-key' not in str(exc)
    assert active.last_evidence.status == 'failed'
from pydantic import TypeAdapter
serialized=TypeAdapter(type(active.last_evidence)).dump_json(active.last_evidence)
assert b'private-fixture-key' not in serialized
assert active.last_evidence.request_observation.status == ('observed' if sys.argv[4] == '200' else 'partial')
assert len(active.last_evidence.request_observation.calls) == 1
assert active.last_evidence.served_model is None
assert active.last_evidence.served_provider is None
"""
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                script,
                str(installed),
                str(opencode_binary),
                str(tmp_path),
                str(status),
            ],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=tmp_path,
            timeout=150,
        )
        assert result.returncode == 0, result.stderr
    assert len(observations) == 1
    body = observations[0][1]
    assert body["temperature"] == 0.2
    expected_reasoning = {
        "effort": {"effort": effort},
        "disabled": {"enabled": False},
        "budget": {"max_tokens": 32},
    }
    assert body["reasoning"] == expected_reasoning[mode]
    if mode == "budget":
        assert body["top_p"] == 0.9
    else:
        assert "top_p" not in body
    assert body["provider"]["allow_fallbacks"] is False
    assert body["max_tokens"] == 128
    assert any(
        "exact author prefix\n" in str(message["content"])
        for message in body["messages"]
    )


from tests.test_opencode_transport import opencode_binary


@pytest.mark.integration
def test_decision_dispatch_is_available_in_the_installed_package(tmp_path):
    from tests.opencode_fixture import install_wheel

    installed = install_wheel(tmp_path)
    script = """
import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
sys.path.insert(1,sys.argv[2])
import aptl
assert Path(aptl.__file__).is_relative_to(Path(sys.argv[1]))
from tests.test_participant_request_dispatch import test_decision_adapters_apply_published_profile_and_prefix
for provider in ('claude','codex'):
    work=Path(sys.argv[3])/provider
    work.mkdir(mode=0o700)
    test_decision_adapters_apply_published_profile_and_prefix(work,provider)
"""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            script,
            str(installed),
            str(Path(__file__).resolve().parents[1]),
            str(tmp_path),
        ],
        text=True,
        capture_output=True,
        cwd=tmp_path,
        timeout=150,
    )
    assert result.returncode == 0, result.stderr
