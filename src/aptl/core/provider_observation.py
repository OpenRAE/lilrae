"""Safe per-request provider facts; observed claims never imply attestation."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Count = Annotated[int, Field(ge=0, le=2**53 - 1)]
Label = Annotated[
    str,
    Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._/:@+-]*$"),
]
Amount = Annotated[float, Field(ge=0, le=1_000_000, allow_inf_nan=False)]


class SafeObservation(BaseModel):
    """Refuse coercion and unknown journal fields without retaining raw errors."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ObservedRoute(SafeObservation):
    only: Annotated[tuple[Label, ...], Field(max_length=16)]
    order: Annotated[tuple[Label, ...], Field(max_length=16)]
    allow_fallbacks: bool
    require_parameters: bool


class ObservedReasoning(SafeObservation):
    effort: Label | None = None
    max_tokens: Count | None = None
    enabled: bool | None = None


class ObservedUsageControl(SafeObservation):
    include_usage: bool | None = None
    include: bool | None = None


class ObservedRequestControls(SafeObservation):
    model: Label
    provider: ObservedRoute
    reasoning: ObservedReasoning | None = None
    temperature: Annotated[float, Field(ge=0, le=2, allow_inf_nan=False)] | None = None
    top_p: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)] | None = None
    seed: Annotated[int, Field(ge=0, le=2**32 - 1)] | None = None
    max_tokens: Annotated[int, Field(ge=1, le=32768)]
    stream: bool
    stream_options: ObservedUsageControl | None = None
    usage: ObservedUsageControl | None = None


class ObservedContext(SafeObservation):
    role: Literal["system", "user", "assistant", "tool"]
    content_sha256: Digest
    authored_prefix_sha256: Digest | None = None


class ProviderResponseObservation(SafeObservation):
    missing_value_reason: Literal["not-reported-or-not-retained"] = (
        "not-reported-or-not-retained"
    )
    generation_id: (
        Annotated[
            str,
            Field(max_length=256, pattern=r"^(gen-|chatcmpl-|resp_)[A-Za-z0-9_-]+$"),
        ]
        | None
    ) = None
    model: Label | None = None
    provider: Label | None = None
    input_tokens: Count | None = None
    output_tokens: Count | None = None
    reasoning_tokens: Count | None = None
    cache_read_tokens: Count | None = None
    cache_write_tokens: Count | None = None
    cost: Amount | None = None
    finish_reason: (
        Literal["stop", "length", "tool_calls", "content_filter", "function_call"]
        | None
    ) = None


class ProviderCallObservation(SafeObservation):
    call_id: Annotated[int, Field(ge=1, le=10_000)]
    requested_at_ms: Count
    completed_at_ms: Count | None = None
    controls: ObservedRequestControls
    context: Annotated[
        tuple[ObservedContext, ...], Field(min_length=1, max_length=4096)
    ]
    http_status: Annotated[int, Field(ge=100, le=599)] | None = None
    state: Literal["dispatched", "completed", "failed", "cancelled"] = "dispatched"
    response: ProviderResponseObservation | None = None


class RequestObservation(SafeObservation):
    schema_version: Literal["lilrae-provider-observation/v1"] = (
        "lilrae-provider-observation/v1"
    )
    status: Literal["observed", "partial", "missing", "invalid", "oversized"]
    observer_sha256: Digest
    calls: Annotated[tuple[ProviderCallObservation, ...], Field(max_length=10_000)] = ()
    native_turn_limit: Annotated[int, Field(ge=1, le=10_000)] | None = None
    source: Literal["provider-fetch"] = "provider-fetch"

    @model_validator(mode="after")
    def bounded_turns(self) -> Self:
        if (
            self.native_turn_limit is not None
            and sum(call.state == "completed" for call in self.calls)
            > self.native_turn_limit
        ):
            raise ValueError("completed native turns exceed the observed limit")
        return self

    def require_fields(self, fields: frozenset[str]) -> None:
        """Qualify only fields observed for every member of this invocation."""
        available = {"outgoing_controls", "prompt_delivery", "request_membership"}
        names = {
            "provider_generation_id": "generation_id",
            "served_model_claim": "model",
            "served_provider_claim": "provider",
            "input_tokens": "input_tokens",
            "output_tokens": "output_tokens",
            "cost": "cost",
        }
        if self.native_turn_limit is not None:
            available.add("native_turn_limit")
        completed = tuple(c for c in self.calls if c.state == "completed")
        for field, attribute in names.items():
            if completed and all(
                c.response is not None and getattr(c.response, attribute) is not None
                for c in completed
            ):
                available.add(field)
        if self.status != "observed" or not self.calls or not fields <= available:
            raise ValueError("required provider request evidence is unavailable")
