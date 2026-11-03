"""Exact prompt content, participant scope and ordered slot verification."""

import hashlib
import pytest
from raes_contracts.canonical import canonical_contract_digest
from raes_contracts.artifact_checksums import checksum_hasher
from raes_contracts.contracts.participant_configuration import (
    ConfigurationOverrideModel,
    realize_participant_configuration,
)
from raes_contracts.participant_control_context import control_context_asset_reference
from tests.participant_request_fixture import owner_fixture, realize


def test_context_metadata_cannot_be_added_to_a_plain_request_target():
    owner, _ = owner_fixture()
    configuration = realize(owner).configuration
    context = next(
        entry.control_context_selection
        for entry in configuration.values
        if entry.target_id == "context.brief"
    )
    values = [
        entry.model_copy(
            update={
                "control_context_selection": context.model_copy(
                    update={"slot_id": "invented"}
                )
            }
        )
        if entry.target_id == owner.model_target
        else entry
        for entry in configuration.values
    ]
    with pytest.raises(ValueError, match="context"):
        owner.validate_and_normalize(
            configuration.model_copy(update={"values": values})
        )


def test_scope_and_stale_descriptor_fail_before_content_resolution():
    owner, scenario = owner_fixture()
    with pytest.raises(ValueError):
        realize(owner, participant="agents.peer")
    scenario.agents["peer"] = type(scenario.agents["operator"])(role="green")
    with pytest.raises(ValueError, match="scope-incompatible"):
        realize(owner.for_scenario(scenario), participant="agents.peer")
    scenario.control_context_assets["brief-terse"].asset_version = "changed"
    with pytest.raises(ValueError):
        realize(owner.for_scenario(scenario))


@pytest.mark.parametrize("algorithm", ["sha256", "sha384", "sha512", "blake3"])
def test_verified_content_requires_exact_bytes_and_participant(algorithm):
    owner, scenario = owner_fixture()
    payload = b"author-owned instruction\n"
    asset = scenario.control_context_assets["brief-terse"]
    hasher = checksum_hasher(algorithm)
    hasher.update(payload)
    asset.content.checksum.algorithm = algorithm
    asset.content.checksum.value = hasher.hexdigest().upper()
    asset.content.size_bytes = len(payload)
    domains = {
        "brief": {
            "control_context_assets.brief-terse": control_context_asset_reference(asset)
        }
    }
    owner = type(owner)(
        catalog=owner.catalog, context_domains=domains, scenario=scenario
    )
    result = realize(owner)
    assert owner.verify_content(
        result, participant_address="agents.operator", contents={"brief": payload}
    ) == (payload.decode(),)
    for address, contents in [
        ("agents.peer", {"brief": payload}),
        ("agents.operator", {"brief": payload + b"\n"}),
        ("agents.operator", {"brief": payload.replace(b"author", b"otherr")}),
        ("agents.operator", {}),
    ]:
        with pytest.raises(ValueError):
            owner.verify_content(result, participant_address=address, contents=contents)


def test_multiple_context_slots_preserve_authored_order_and_exact_bytes():
    from aptl.core.participant_requests import ParticipantRequestOwner

    original, scenario = owner_fixture()
    data = {"first": b"first instruction\n", "later": b"second instruction\n"}
    domains = {}
    for slot, asset_name in (("first", "brief-terse"), ("later", "brief-rich")):
        asset = scenario.control_context_assets[asset_name]
        asset.content.checksum.value = hashlib.sha256(data[slot]).hexdigest()
        asset.content.size_bytes = len(data[slot])
        domains[slot] = {
            f"control_context_assets.{asset_name}": control_context_asset_reference(
                asset
            )
        }
    catalog = original.catalog.model_copy(
        update={
            "profiles": tuple(
                profile.model_copy(update={"context_order": ("later", "first")})
                for profile in original.catalog.profiles
            )
        }
    )
    owner = ParticipantRequestOwner(
        catalog=catalog, context_domains=domains, scenario=scenario
    )
    profile = owner.catalog.profiles[0]
    values = {
        owner.model_target: profile.model,
        "request.profile": profile.reference,
        "request.profile_digest": profile.digest,
        "context.first": "control_context_assets.brief-terse",
        "context.later": "control_context_assets.brief-rich",
    }
    result = realize_participant_configuration(
        participant_address="agents.operator",
        manifest=owner.manifest,
        manifest_ref="participant-implementation-manifests.consumer",
        manifest_digest=canonical_contract_digest(owner.manifest),
        overrides=[
            ConfigurationOverrideModel(
                target_id=key, value={"kind": "literal", "value": value}
            )
            for key, value in values.items()
        ],
        validator=owner,
    )
    assert owner.verify_content(
        result, participant_address="agents.operator", contents=data
    ) == (data["later"].decode(), data["first"].decode())
