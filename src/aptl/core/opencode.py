"""Pinned OpenCode build, explicit route, and safe invocation evidence."""

from dataclasses import dataclass
import re
from urllib.parse import SplitResult, urlsplit

from typing import Literal
from aptl.core.provider_observation import RequestObservation


def _loopback_fixture(url: SplitResult, path: str = "/api/v1") -> bool:
    """Admit only explicit loopback ports for offline provider qualification."""
    return (
        url.scheme == "http"
        and url.hostname in {"127.0.0.1", "::1"}
        and url.path == path
        and url.port is not None
    )


def is_loopback_gateway(endpoint: str, *, path: str) -> bool:
    """Approve only explicit local fake-provider endpoints without credential locators."""
    url = urlsplit(endpoint)
    return (
        _loopback_fixture(url, path)
        and url.username is None
        and url.password is None
        and not url.query
        and not url.fragment
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
class VertexRoute:
    """The Vertex AI global endpoint for one Google Cloud project."""

    project: str

    def __post_init__(self) -> None:
        raise ValueError("Vertex AI route is not admitted")


ParticipantRoute = OpenRouterRoute | VertexRoute


@dataclass(frozen=True)
class NativeStepObservation:
    """One native step report, without private text or provider attestation."""

    message_id: str
    step_id: str
    finish_reason: str
    created_at_ms: int
    completed_at_ms: int
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    cache_read_tokens: int | None
    cache_write_tokens: int | None
    estimated_cost: float | None


@dataclass(frozen=True)
class NativeHistoryObservation:
    """Allowlisted delivery facts from one private native session database."""

    status: Literal[
        "observed",
        "partial",
        "missing",
        "invalid",
        "oversized",
        "uncheckpointed",
        "unsupported-platform",
    ]
    session_id: str | None = None
    user_message_id: str | None = None
    prompt_matches: bool | None = None
    recorded_model: str | None = None
    prompt_sha256: str | None = None
    authored_placement: Literal["native-user-text"] | None = None
    steps: tuple[NativeStepObservation, ...] = ()
    source: Literal["native-session-history"] = "native-session-history"
    unavailable_fields: tuple[str, ...] = (
        "outgoing_controls",
        "provider_generation_id",
        "served_model",
        "served_provider",
        "billing_cost",
    )

    def require_fields(self, fields: frozenset[str]) -> None:
        """Refuse a capture claim that the observed native source cannot satisfy."""
        available = {
            "prompt_delivery",
            "recorded_model",
            "native_session",
            "native_steps",
        }
        if self.status != "observed" or not fields <= available:
            raise ValueError("required native participant evidence is unavailable")


@dataclass(frozen=True)
class OpenCodeTrialScope:
    """Sealed trial and retained attempt coordinates supplied by trusted entry code."""

    run_id: str
    execution_attempt_id: str
    plan_entry_id: str


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
    native_history: NativeHistoryObservation | None = None
    request_observation: RequestObservation | None = None
    participant_address: str | None = None
    configuration_digest: str | None = None
    trial_scope: OpenCodeTrialScope | None = None
