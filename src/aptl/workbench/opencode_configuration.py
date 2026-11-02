"""Provider-native OpenCode configuration and minimal launch environment."""

from collections.abc import Mapping
import os
from pathlib import Path

from aptl.core.opencode import OpenRouterRoute


def render_opencode_config(
    model: str,
    route: OpenRouterRoute,
    permissions: Mapping[str, str],
    servers: dict[str, object],
) -> dict[str, object]:
    """Serialize admitted route and tool inputs into the upstream config shape."""
    return {
        "model": model,
        "small_model": model,
        "enabled_providers": ["openrouter"],
        "provider": {
            "openrouter": {
                "whitelist": [model.removeprefix("openrouter/")],
                "options": {
                    "baseURL": route.endpoint,
                    "apiKey": "{env:OPENROUTER_API_KEY}",
                },
                "models": {
                    model.removeprefix("openrouter/"): {
                        "options": {
                            "provider": {
                                "only": [route.serving_provider],
                                "order": [route.serving_provider],
                                "allow_fallbacks": False,
                                "require_parameters": True,
                            }
                        }
                    }
                },
            }
        },
        "compaction": {"auto": False, "prune": False},
        "autoupdate": False,
        "share": "disabled",
        "permission": permissions,
        "mcp": servers,
        "plugin": [],
        "instructions": [],
        "snapshot": False,
    }


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
