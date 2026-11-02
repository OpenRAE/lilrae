"""Closed installed-provider model identity validation for project configuration."""

import re

_PARTICIPANT_MODEL_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:/@-]{0,127}$")
_IMMUTABLE_PARTICIPANT_MODEL_PATTERNS = {
    "opencode": re.compile(
        r"^openrouter/[a-zA-Z0-9][a-zA-Z0-9._:/@-]{0,116}$", flags=re.ASCII
    ),
    "claude": re.compile(
        r"^claude-(?:[a-z0-9-]+[-@]\d{8}|(?:sonnet|opus|haiku)-[1-9]\d*)$",
        flags=re.ASCII,
    ),
    "codex": re.compile(
        r"^(?:codex-[a-z0-9._-]+|gpt-[a-z0-9._-]+|o\d[a-z0-9._-]*)"
        r"-\d{4}-\d{2}-\d{2}$",
        flags=re.ASCII,
    ),
}


def validate_installed_participant_model_id(provider: str, value: str) -> str:
    """Validate one explicit, non-secret installed-provider model identity."""

    immutable_pattern = _IMMUTABLE_PARTICIPANT_MODEL_PATTERNS.get(provider)
    if (
        immutable_pattern is None
        or not isinstance(value, str)
        or not _PARTICIPANT_MODEL_PATTERN.fullmatch(value)
        or not immutable_pattern.fullmatch(value)
    ):
        raise ValueError("installed participant model identifier is invalid")
    return value
