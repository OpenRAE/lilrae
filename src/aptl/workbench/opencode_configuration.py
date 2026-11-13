"""Provider-native OpenCode configuration and minimal launch environment."""

import math
import os
from collections.abc import Mapping
from pathlib import Path

from aptl.core._participant_model_ids import validate_installed_participant_model_id
from aptl.core.opencode import (
    OpenRouterRoute,
    ParticipantRoute,
    VertexRoute,
)
from aptl.core.participant_requests.profiles import RequestProfile

_OPENROUTER_PREFIX = "openrouter/"


def opencode_arguments(executable: Path, model: str) -> tuple[str, ...]:
    """Build fixed invocation arguments for the admitted executable and model."""
    return (
        str(executable),
        "run",
        "--format",
        "json",
        "--model",
        model,
        "--title",
        "lilrae-participant",
    )


def render_opencode_config(
    model: str,
    route: ParticipantRoute,
    permissions: Mapping[str, str],
    servers: dict[str, object],
    *,
    request_profile: RequestProfile | None = None,
    max_steps: int | None = None,
) -> dict[str, object]:
    """Serialize admitted route and tool inputs into the upstream config shape."""
    if request_profile is not None and not isinstance(route, OpenRouterRoute):
        raise ValueError("participant request profiles need an OpenRouter route")
    config = {
        "model": model,
        "small_model": model,
        "enabled_providers": [route.provider_id],
        "provider": {route.provider_id: route.provider_config(model)},
        "compaction": {"auto": False, "prune": False},
        "autoupdate": False,
        "share": "disabled",
        "permission": permissions,
        "mcp": servers,
        "plugin": [],
        "instructions": [],
        "snapshot": False,
    }
    if request_profile is not None:
        profile = request_profile
        model_config = config["provider"]["openrouter"]["models"][
            model.removeprefix(_OPENROUTER_PREFIX)
        ]
        native = model_config["options"]
        if profile.reasoning_mode == "effort":
            native["reasoning"] = {"effort": profile.reasoning_effort.value}
        elif profile.reasoning_mode == "budget":
            native["reasoning"] = {"max_tokens": profile.reasoning_budget.value}
        elif profile.reasoning_mode == "disabled":
            native["reasoning"] = {"enabled": False}
        model_config["temperature"] = profile.temperature.value is not None
        agent = {}
        if profile.temperature.value is not None:
            agent["temperature"] = profile.temperature.value
        if profile.top_p.value is not None:
            agent["top_p"] = profile.top_p.value
        config["agent"] = {"build": agent}
    if max_steps is not None:
        config.setdefault("agent", {}).setdefault("build", {})["steps"] = max_steps
    return config


def opencode_environment(
    work: Path, credentials: Mapping[str, str], max_output_tokens: int
) -> dict[str, str]:
    """Build a fresh child environment without inheriting host configuration."""
    return {
        "PATH": os.defpath,
        "HOME": str(work),
        "NO_COLOR": "1",
        "XDG_CONFIG_HOME": str(work / "config"),
        "XDG_DATA_HOME": str(work / "data"),
        "XDG_STATE_HOME": str(work / "state"),
        "XDG_CACHE_HOME": str(work / "cache"),
        "OPENCODE_CONFIG": str(work / "opencode.json"),
        "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
        "OPENCODE_DISABLE_CLAUDE_CODE": "true",
        "OPENCODE_DISABLE_EXTERNAL_SKILLS": "true",
        "OPENCODE_DISABLE_DEFAULT_PLUGINS": "true",
        "OPENCODE_DISABLE_AUTOUPDATE": "true",
        "OPENCODE_DISABLE_LSP_DOWNLOAD": "true",
        "OPENCODE_DISABLE_MODELS_FETCH": "true",
        "OPENCODE_PURE": "true",
        "OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX": str(max_output_tokens),
        **credentials,
    }


PROVIDER_CREDENTIAL_NAMES = OpenRouterRoute.environment_names | VertexRoute.environment_names


def validate_provider_environment(
    environment: Mapping[str, str], route: ParticipantRoute | None = None
) -> None:
    """Permit only the route's explicit provider inputs without ambient configuration."""
    admitted = route.environment_names if route is not None else OpenRouterRoute.environment_names
    if set(environment) - admitted:
        raise ValueError("participant provider environment is not admitted")
    if any(
        not isinstance(value, str) or not value or "\0" in value
        for value in environment.values()
    ):
        raise ValueError("participant provider environment is invalid")


def validate_invocation_inputs(
    model: str,
    prompt: str,
    timeout_seconds: float,
    max_output_bytes: int,
    max_output_tokens: int,
) -> None:
    """Bound participant inputs before any process or tool probe starts."""
    validate_installed_participant_model_id("opencode", model)
    if not prompt.strip() or len(prompt.encode()) > 128_000:
        raise ValueError("participant model or prompt is invalid")
    if (
        not math.isfinite(timeout_seconds)
        or not 0 < timeout_seconds <= 3600
        or not 0 < max_output_bytes <= 1_000_000
        or type(max_output_tokens) is not int
        or not 1 <= max_output_tokens <= 32768
    ):
        raise ValueError("participant execution limits are invalid")
