"""Configuration commits each participant's model and exact prompt bytes."""

from aptl.workbench.lilrae_opencode import OpenCodeOptions

import hashlib

import pytest
from raes_contracts.participant_configuration import (
    ConfigurationOverrideModel,
    realize_participant_configuration,
)
from raes_contracts.satisfiability import canonical_contract_digest


def configuration(
    model="provider/model",
    prompt="red task",
    *,
    role="red",
    manifest_ref="participant-implementation-manifests.opencode.v1",
):
    from aptl.backends.lilrae_participant_configuration import (
        opencode_manifest,
        OpenCodeConfigurationValidator,
    )

    manifest = opencode_manifest(version="1.0.0")
    values = {
        "model": model,
        "prompt_ref": "content.red-prompt@v1",
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "timeout_seconds": 37,
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
            supported_models=frozenset({"provider/model", "provider/other"})
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
        options=OpenCodeOptions(
            executable=Path("/bin/true"),
            work_root=tmp_path,
            environment={},
            runner=runner,
        ),
        configuration=result,
        manifest=manifest,
        prompt="red task",
        prompt_ref="content.red-prompt@v1",
        supported_models=frozenset({"provider/model"}),
    )
    executor("action", Event())
    assert runner.calls[0][1]["stdin"] == b"red task"
    assert runner.calls[0][1]["timeout_seconds"] == 37
    assert "provider/model" in runner.calls[0][0]
    options = OpenCodeOptions(executable=Path("/bin/true"), work_root=tmp_path)
    supported_models = frozenset({"provider/model"})
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
        configuration(model="provider/unknown")
    _, first = configuration()
    _, second = configuration(prompt="changed prompt")
    _, third = configuration(model="provider/other")
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
