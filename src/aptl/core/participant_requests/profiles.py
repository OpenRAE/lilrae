"""Closed, reviewed native request profiles; portable results remain RAES-owned."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from raes_contracts.canonical import canonical_json_digest

from aptl.core._participant_model_ids import validate_installed_participant_model_id
from aptl.core.opencode import OpenRouterRoute, is_loopback_gateway

Label = Annotated[
    str, Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:-]*$")
]
Count = Annotated[int, Field(ge=1, le=32768)]
Temperature = Annotated[float, Field(ge=0, le=2, allow_inf_nan=False)]
Probability = Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)]


class ClosedModel(BaseModel):
    """Reject implicit fields and coercion at the trusted catalog boundary."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ParameterPolicy[T](ClosedModel):
    """An explicit native value or a deliberate, inspectable omission."""

    state: Literal["set", "locked", "omit", "unsupported", "provider-managed"]
    value: T | None

    @model_validator(mode="after")
    def consistent_value(self) -> ParameterPolicy[T]:
        if (self.value is not None) != (self.state in {"set", "locked"}):
            raise ValueError("request parameter value and disposition disagree")
        return self


class RequestProfile(ClosedModel):
    """One reviewed exact model/control combination, without native escape hatches."""

    profile_id: Label
    version: Label
    review_ref: Annotated[
        str,
        Field(
            min_length=1, max_length=256, pattern=r"^urn:[a-zA-Z0-9][a-zA-Z0-9:._/-]*$"
        ),
    ]
    model: str
    gateway: Literal["anthropic", "openai", "openrouter"]
    gateway_endpoint: str
    serving_provider: str
    no_fallback: StrictBool
    reasoning_mode: Literal["unsupported", "disabled", "effort", "budget"]
    reasoning_effort: ParameterPolicy[Label]
    reasoning_budget: ParameterPolicy[Count]
    temperature: ParameterPolicy[Temperature]
    top_p: ParameterPolicy[Probability]
    seed: ParameterPolicy[Annotated[int, Field(ge=0, le=2**32 - 1)]]
    output_limit: ParameterPolicy[Count]
    limit_scope: Literal["output", "combined-generation", "provider-managed"]
    usage_policy: Literal["when-reported"]
    context_order: Annotated[tuple[Label, ...], Field(min_length=1, max_length=16)]
    context_placement: Literal["stdin-prefix"]

    @property
    def reference(self) -> str:
        return f"{self.profile_id}@{self.version}"

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json"))

    @model_validator(mode="after")
    def explicit_controls(self) -> RequestProfile:
        if not self.no_fallback or self.seed.state != "unsupported":
            raise ValueError("fallback or seed requests are unsupported")
        if len(set(self.context_order)) != len(self.context_order):
            raise ValueError("context slots must be unique")
        expected = {
            "unsupported": ("unsupported", "unsupported"),
            "disabled": ("omit", "omit"),
            "effort": ("set", "omit"),
            "budget": ("omit", "set"),
        }[self.reasoning_mode]
        actual = tuple(
            "set" if control.state == "locked" else control.state
            for control in (self.reasoning_effort, self.reasoning_budget)
        )
        if actual != expected:
            raise ValueError("reasoning mode and parameter dispositions disagree")
        if (self.limit_scope == "provider-managed") != (
            self.output_limit.state == "provider-managed"
        ):
            raise ValueError("generation limit scope and disposition disagree")
        return self


class RequestCatalog(ClosedModel):
    """Trusted owner-reviewed domain, supplied by consumer entry assembly."""

    provider: Literal["claude", "codex", "opencode"]
    implementation_version: Label
    build_version: Label
    executable_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    profiles: Annotated[tuple[RequestProfile, ...], Field(min_length=1, max_length=256)]

    @model_validator(mode="after")
    def supported_native_controls(self) -> RequestCatalog:
        references = [profile.reference for profile in self.profiles]
        if len(set(references)) != len(references):
            raise ValueError("request profile versions must be unique")
        for profile in self.profiles:
            validate_installed_participant_model_id(self.provider, profile.model)
            self._validate_profile(profile)
        return self

    def _validate_profile(self, profile: RequestProfile) -> None:
        gateway = {"claude": "anthropic", "codex": "openai", "opencode": "openrouter"}[
            self.provider
        ]
        if profile.gateway != gateway:
            raise ValueError("request gateway is unsupported by this implementation")
        endpoints = {
            "anthropic": "https://api.anthropic.com",
            "openai": "https://api.openai.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
        }
        if (
            self.provider != "opencode"
            and profile.gateway_endpoint != endpoints[gateway]
            and not is_loopback_gateway(
                profile.gateway_endpoint,
                path="" if self.provider == "claude" else "/v1",
            )
        ):
            raise ValueError("request gateway endpoint is not approved")
        efforts = {
            "claude": {"low", "medium", "high", "xhigh", "max"},
            "codex": {
                "none",
                "minimal",
                "low",
                "medium",
                "high",
                "xhigh",
            },
            "opencode": {"none", "minimal", "low", "medium", "high", "xhigh"},
        }
        if (
            profile.reasoning_mode == "effort"
            and profile.reasoning_effort.value not in efforts[self.provider]
        ):
            raise ValueError("reasoning effort is unsupported by this implementation")
        if self.provider != "opencode":
            if profile.serving_provider != gateway:
                raise ValueError("exclusive alternate serving routes are unsupported")
            if any(
                control.state != "unsupported"
                for control in (profile.temperature, profile.top_p)
            ):
                raise ValueError("installed CLI sampling requests are unsupported")
            if profile.output_limit.state != "provider-managed":
                raise ValueError("installed CLI generation limits are provider-managed")
        elif (
            profile.output_limit.state not in {"set", "locked"}
            or profile.limit_scope == "provider-managed"
        ):
            raise ValueError("OpenCode requires an explicit output limit")
        if self.provider == "codex" and profile.reasoning_mode == "budget":
            raise ValueError("Codex reasoning budgets are unsupported")
        if self.provider == "claude" and profile.reasoning_mode in {
            "disabled",
            "budget",
        }:
            raise ValueError(
                "Claude disabled reasoning and budgets are unsupported by this adapter"
            )
        if (
            self.provider == "opencode"
            and profile.reasoning_mode == "budget"
            and (
                profile.limit_scope != "combined-generation"
                or profile.reasoning_budget.value >= profile.output_limit.value
            )
        ):
            raise ValueError("reasoning budget must fit the combined generation limit")
        if self.provider == "opencode" and any(
            control.state == "provider-managed"
            for control in (profile.temperature, profile.top_p)
        ):
            raise ValueError("sampling must be explicit or deliberately omitted")
        if self.provider == "opencode":
            OpenRouterRoute(
                endpoint=profile.gateway_endpoint,
                serving_provider=profile.serving_provider,
            )
