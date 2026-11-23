"""Consumer-owned catalog and SDL assets for participant request tests."""

from pathlib import Path

import yaml
from raes import Scenario
from raes_contracts.canonical import canonical_contract_digest
from raes_contracts.contracts.participant_configuration import (
    ConfigurationOverrideModel,
    realize_participant_configuration,
)
from raes_contracts.participant_control_context import control_context_asset_reference


def profile_data(provider="opencode", *, model=None, version="v1"):
    omitted = {"state": "unsupported", "value": None}
    return {
        "profile_id": "consumer-choice",
        "version": version,
        "review_ref": "urn:consumer:review:17",
        "model": model
        or {
            "opencode": "openrouter/author/model:free",
            "codex": "gpt-5.2-codex",
            "claude": "claude-sonnet-4-5",
        }[provider],
        "gateway": {"opencode": "openrouter", "codex": "openai", "claude": "anthropic"}[
            provider
        ],
        "gateway_endpoint": {
            "opencode": "https://openrouter.ai/api/v1",
            "codex": "https://api.openai.com/v1",
            "claude": "https://api.anthropic.com",
        }[provider],
        "serving_provider": "consumer-route"
        if provider == "opencode"
        else {"codex": "openai", "claude": "anthropic"}[provider],
        "no_fallback": True,
        "reasoning_mode": "unsupported",
        "reasoning_effort": omitted,
        "reasoning_budget": omitted,
        "temperature": omitted,
        "top_p": omitted,
        "seed": omitted,
        "output_limit": {"state": "set", "value": 128}
        if provider == "opencode"
        else {"state": "provider-managed", "value": None},
        "limit_scope": "output" if provider == "opencode" else "provider-managed",
        "usage_policy": "when-reported",
        "context_order": ("brief",),
        "context_placement": "stdin-prefix",
    }


def owner_fixture(provider="opencode", *, changed_profile=False):
    from aptl.core.participant_requests import ParticipantRequestOwner, RequestCatalog

    family = yaml.safe_load(
        (
            Path(__file__).parent
            / "fixtures/structural_family/pack/sdl/structural-fixture.sdl.yaml"
        ).read_text()
    )
    scenario = Scenario.model_validate(family)
    profiles = (
        profile_data(provider),
        profile_data(
            provider,
            model={
                "opencode": "openrouter/author/other",
                "claude": "claude-haiku-4-5",
                "codex": "gpt-5-nano",
            }[provider],
            version="v2",
        ),
    )
    if changed_profile:
        profiles[0]["review_ref"] = "urn:consumer:review:18"
    catalog = RequestCatalog(
        provider=provider,
        implementation_version="1.0.0",
        build_version="1.19.5" if provider == "opencode" else "2.0.0",
        executable_sha256="a" * 64,
        profiles=profiles,
    )
    domains = {
        "brief": {
            f"control_context_assets.{name}": control_context_asset_reference(asset)
            for name, asset in scenario.control_context_assets.items()
        }
    }
    owner = ParticipantRequestOwner(
        catalog=catalog, context_domains=domains, scenario=scenario
    )
    return owner, scenario


def realize(
    owner,
    *,
    participant="agents.operator",
    profile_index=0,
    prompt="brief-terse",
    **changes,
):
    profile = owner.catalog.profiles[profile_index]
    values = {
        owner.model_target: profile.model,
        "request.profile": profile.profile_id + "@" + profile.version,
        "request.profile_digest": profile.digest,
        "context.brief": f"control_context_assets.{prompt}",
    }
    values.update(changes)
    manifest = owner.manifest
    return realize_participant_configuration(
        participant_address=participant,
        manifest=manifest,
        manifest_ref="participant-implementation-manifests.consumer",
        manifest_digest=canonical_contract_digest(manifest),
        overrides=[
            ConfigurationOverrideModel(
                target_id=k, value={"kind": "literal", "value": v}
            )
            for k, v in values.items()
        ],
        validator=owner,
    )
