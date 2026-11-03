"""Typed native controls for owner-verified decision participant requests."""

import hashlib
import json
from pathlib import Path

from aptl.core.participant_requests.request import ParticipantRequest
from aptl.core.participant_requests.binding import ParticipantRequestBinding
from aptl.core.opencode import OpenCodeBuild, OpenRouterRoute
from aptl.workbench.process import AgentExecutionError


def _validate_binding(
    request: ParticipantRequest | None, binding: ParticipantRequestBinding | None
) -> None:
    """Require the independent binding for each expanded request."""
    if request is None:
        if binding is not None:
            raise ValueError("participant request binding has no request")
    elif binding is None:
        raise ValueError("participant request requires a trusted binding")
    else:
        binding.validate(request)


def validate_request(
    request: ParticipantRequest | None,
    *,
    provider: str,
    model: str,
    executable: Path,
    binding: ParticipantRequestBinding | None = None,
) -> None:
    """Refuse changed executable or selection before any provider operation."""
    try:
        _validate_binding(request, binding)
    except ValueError:
        raise AgentExecutionError("participant request binding was refused") from None
    if request is None:
        return
    try:
        with executable.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError:
        raise AgentExecutionError("participant executable is unavailable") from None
    if (
        request.provider != provider
        or request.profile.model != model
        or digest != request.executable_sha256
    ):
        raise AgentExecutionError(
            "participant request or executable differs from its pin"
        )


def request_environment(request: ParticipantRequest | None) -> dict[str, str]:
    """Render only fixed, typed Claude controls into the minimal environment."""
    if request is None or request.provider != "claude":
        return {}
    profile = request.profile
    return {"ANTHROPIC_BASE_URL": profile.gateway_endpoint}


def request_arguments(request: ParticipantRequest | None) -> tuple[str, ...]:
    """Native configuration is generated from a closed profile, never passed through."""
    if request is None:
        return ()
    profile = request.profile
    if request.provider == "claude":
        args = (
            "--settings",
            json.dumps(
                {
                    "availableModels": [profile.model],
                    "fallbackModel": [],
                    "switchModelsOnFlag": False,
                }
            ),
        )
        if profile.reasoning_mode == "effort":
            args += ("--effort", profile.reasoning_effort.value)
        return args
    args = (
        "--config",
        'model_provider="lilrae-openai"',
        "--config",
        'model_providers.lilrae-openai.name="OpenAI"',
        "--config",
        'model_providers.lilrae-openai.wire_api="responses"',
        "--config",
        'model_providers.lilrae-openai.env_key="CODEX_API_KEY"',
        "--config",
        "model_providers.lilrae-openai.base_url="
        + json.dumps(profile.gateway_endpoint),
    )
    if profile.reasoning_mode in {"effort", "disabled"}:
        effort = (
            profile.reasoning_effort.value
            if profile.reasoning_mode == "effort"
            else "none"
        )
        args += ("--config", "model_reasoning_effort=" + json.dumps(effort))
    return args


def validate_opencode_request(
    request: ParticipantRequest | None,
    *,
    model: str,
    prompt: str,
    build: OpenCodeBuild,
    route: OpenRouterRoute,
    output_limit: int,
    assistant_turn_limit: int | None = None,
    binding: ParticipantRequestBinding | None = None,
) -> None:
    """Keep the native OpenCode delivery equal to the owner-verified request."""
    _validate_binding(request, binding)
    if request is None:
        return
    turns = request.profile.assistant_turn_limit
    if turns is not None and turns.value != assistant_turn_limit:
        raise ValueError("participant native assistant turn limit differs from its pin")
    if (
        request.provider != "opencode"
        or request.profile.model != model
        or request.prompt != prompt
        or request.executable_sha256 != build.executable_sha256
        or request.build_version != build.version
        or request.profile.gateway_endpoint != route.endpoint
        or request.profile.serving_provider != route.serving_provider
        or request.profile.output_limit.value != output_limit
    ):
        raise ValueError("participant request differs from its installed delivery")
