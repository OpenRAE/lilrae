"""Configuration commits each participant's model and exact prompt bytes."""

from tests.opencode_fixture import synthetic_options

import hashlib

import pytest
from raes_contracts.contracts.participant_configuration import ConfigurationOverrideModel, realize_participant_configuration
from raes_contracts.canonical import canonical_contract_digest


def configuration(
    model="openrouter/model",
    prompt="red task",
    *,
    role="red",
    manifest_ref="participant-implementation-manifests.opencode.v1",
):
    from aptl.backends.lilrae_participant_configuration import (
        opencode_manifest,
        OpenCodeConfigurationValidator,
    )

    from aptl.core.opencode import OpenCodeBuild
    from pathlib import Path

    manifest = opencode_manifest(
        version="1.0.0",
        build=OpenCodeBuild(
            version="1.19.5",
            executable_sha256=hashlib.sha256(
                Path("/bin/true").read_bytes()
            ).hexdigest(),
        ),
    )
    values = {
        "model": model,
        "prompt_ref": "content.red-prompt@v1",
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "timeout_seconds": 37,
        "gateway_endpoint": "https://openrouter.ai/api/v1",
        "serving_provider": "test-provider",
        "max_output_tokens": 128,
    }
    result = realize_participant_configuration(
        participant_address=f"participant.behavior.{role}",
        manifest=manifest,
        manifest_ref=manifest_ref,
        manifest_digest=canonical_contract_digest(manifest),
        overrides=[
            ConfigurationOverrideModel(
                target_id=key, value={"kind": "literal", "value": value}
            )
            for key, value in values.items()
        ],
        validator=OpenCodeConfigurationValidator(
            supported_models=frozenset({"openrouter/model", "openrouter/other"})
        ),
    )
    return manifest, result


def test_pinned_prompt_and_selected_model_reach_executor(tmp_path):
    from aptl.backends.lilrae_participant_configuration import (
        configured_opencode_executor,
    )
    from tests.test_lilrae_opencode import RecordingRunner
    from threading import Event
    from pathlib import Path

    runner = RecordingRunner()
    manifest, result = configuration()
    executor = configured_opencode_executor(
        options=synthetic_options(
            executable=Path("/bin/true"),
            work_root=tmp_path,
            environment={},
            runner=runner,
        ),
        configuration=result,
        manifest=manifest,
        prompt="red task",
        prompt_ref="content.red-prompt@v1",
        supported_models=frozenset({"openrouter/model"}),
    )
    executor("action", Event())
    assert runner.calls[0][1]["stdin"] == b"red task"
    assert runner.calls[0][1]["timeout_seconds"] == 37
    assert "openrouter/model" in runner.calls[0][0]
    options = synthetic_options(executable=Path("/bin/true"), work_root=tmp_path)
    supported_models = frozenset({"openrouter/model"})
    with pytest.raises(ValueError, match="prompt"):
        configured_opencode_executor(
            options=options,
            configuration=result,
            manifest=manifest,
            prompt="peer task",
            prompt_ref="content.red-prompt@v1",
            supported_models=supported_models,
        )


def test_model_domain_and_independent_configuration_commitments():
    with pytest.raises(ValueError, match="model"):
        configuration(model="openrouter/unknown")
    _, first = configuration()
    _, second = configuration(prompt="changed prompt")
    _, third = configuration(model="openrouter/other")
    assert (
        len(
            {
                first.configuration_digest,
                second.configuration_digest,
                third.configuration_digest,
            }
        )
        == 3
    )


def test_configuration_refuses_route_changed_after_admission(tmp_path):
    from dataclasses import replace
    from pathlib import Path
    from aptl.core.opencode import OpenRouterRoute
    from aptl.backends.lilrae_participant_configuration import (
        configured_opencode_executor,
    )

    manifest, result = configuration()
    settings = synthetic_options(executable=Path("/bin/true"), work_root=tmp_path)
    settings = replace(
        settings,
        route=OpenRouterRoute(
            endpoint="https://openrouter.ai/api/v1", serving_provider="different"
        ),
    )
    with pytest.raises(ValueError, match="route"):
        configured_opencode_executor(
            options=settings,
            configuration=result,
            manifest=manifest,
            prompt="red task",
            prompt_ref="content.red-prompt@v1",
            supported_models=frozenset({"openrouter/model"}),
        )
