"""Pinned OpenCode build, explicit route, and safe invocation evidence."""

from dataclasses import dataclass
import re
from urllib.parse import SplitResult, urlsplit


def _loopback_fixture(url: SplitResult) -> bool:
    """Admit only explicit loopback ports for offline provider qualification."""
    return (
        url.scheme == "http"
        and url.hostname in {"127.0.0.1", "::1"}
        and url.path == "/api/v1"
        and url.port is not None
    )


@dataclass(frozen=True)
class OpenCodeBuild:
    """Operator-admitted executable bytes, distinct from adapter/model identity."""

    version: str
    executable_sha256: str

    def __post_init__(self) -> None:
        if not re.fullmatch(
            r"\d+\.\d+\.\d+", self.version, flags=re.ASCII
        ) or not re.fullmatch(r"[0-9a-f]{64}", self.executable_sha256):
            raise ValueError("OpenCode build identity is invalid")


SUPPORTED_OPENCODE_BUILD = OpenCodeBuild(
    version="1.19.5",
    executable_sha256="7df4e4136301f16589b0f30bf91a61380fca5f8ef22dd36570f5ebe1d4ec802c",
)


@dataclass(frozen=True)
class OpenRouterRoute:
    """One approved gateway endpoint and one exclusive serving provider."""

    endpoint: str
    serving_provider: str

    def __post_init__(self) -> None:
        url = urlsplit(self.endpoint)
        live = self.endpoint == "https://openrouter.ai/api/v1"
        # Loopback supports hermetic provider qualification without TLS bypasses.
        fixture = _loopback_fixture(url)
        if (
            not (live or fixture)
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or not re.fullmatch(r"[a-z0-9][a-z0-9_./:-]{0,127}", self.serving_provider)
        ):
            raise ValueError("OpenCode route is not admitted")


@dataclass(frozen=True)
class OpenCodeInvocationEvidence:
    """Allowlisted facts; no prompt, output text, credential, or raw event."""

    action_id: str
    build: OpenCodeBuild
    requested_model: str
    endpoint: str
    requested_serving_provider: str
    prompt_sha256: str
    status: str
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    stdout_sha256: str | None = None
    partial_text_sha256: str | None = None
    session_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost: float | None = None
    finish_reason: str | None = None
    served_model: str | None = None
    served_provider: str | None = None
    cleanup_residual: tuple[str, ...] | None = None
    tool_transport_cleanup: str | None = None
