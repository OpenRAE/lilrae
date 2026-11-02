"""Strict platform-only policy contract for issue #822."""

import hashlib
import json

import pytest
from pydantic import ValidationError

from aptl.core.appliance_boundary import (
    ApplianceBoundaryBinding,
    ApplianceBoundaryPolicy,
    load_boundary_policy,
    render_egress_proxy_policy,
)
from aptl.appliance.policy import full_techvault_boundary_policy
from aptl.workbench import ProfileId, profile_for


def _policy() -> dict[str, object]:
    return {
        "schema_version": "aptl.appliance-boundary/v1",
        "policy_id": "participant-default",
        "generation": 4,
        "workbench_policy_version": "participant-workbench-profile/v1",
        "default_deny": True,
        "platform_networks": {
            "participant": "org.aptl.appliance.network=participant",
            "management": "org.aptl.appliance.network=management",
            "egress": "org.aptl.appliance.network=egress",
        },
        "platform_anchors": {
            "participant": "org.aptl.appliance.zone=participant",
            "management": "org.aptl.appliance.zone=management",
            "egress": "org.aptl.appliance.zone=egress",
        },
        "fixed_crossings": [
            {
                "source": "management",
                "destination": "egress",
                "protocol": "tcp",
                "ports": [3128],
                "purpose": "model-provider-proxy",
            }
        ],
        "egress_authorities": [
            {
                "source": "egress",
                "authority": "api.example.test",
                "protocol": "tcp",
                "port": 443,
                "purpose": "model-provider",
                "resolution": "proxy-resolved-all-global",
                "failure_disposition": "deny",
            }
        ],
        "egress_proxy_limits": {
            "max_connections": 32,
            "max_header_bytes": 4096,
            "header_timeout_seconds": 5,
            "connect_timeout_seconds": 10,
            "idle_timeout_seconds": 60,
        },
        "guest_publications": [
            {
                "audience": "participant",
                "address": "127.0.0.1",
                "port": 443,
                "protocol": "tcp",
            }
        ],
        "docker_authority": {
            "allowed_holder_labels": ["org.aptl.appliance.role=deployment-authority"],
            "require_guest_daemon": True,
        },
    }


def test_policy_is_platform_only_strict_and_default_deny() -> None:
    policy = ApplianceBoundaryPolicy.model_validate(_policy())

    assert policy.default_deny is True
    assert policy.egress_authorities[0].authority == "api.example.test"
    assert policy.workbench_policy_version == profile_for(ProfileId.RED).policy_version
    assert (
        policy.workbench_policy_version
        == profile_for(ProfileId.GUIDED_BLUE).policy_version
    )
    assert policy.workbench_policy_version == profile_for(ProfileId.BLUE).policy_version

    scenario_copy = _policy()
    scenario_copy["scenario_networks"] = ["red", "blue"]
    with pytest.raises(ValidationError):
        ApplianceBoundaryPolicy.model_validate(scenario_copy)

    fail_open = _policy()
    fail_open["default_deny"] = False
    with pytest.raises(ValidationError):
        ApplianceBoundaryPolicy.model_validate(fail_open)


def test_policy_digest_is_bound_by_release_projection(tmp_path) -> None:
    payload = json.dumps(_policy(), sort_keys=True, separators=(",", ":")).encode()
    policy_path = tmp_path / "boundary.json"
    policy_path.write_bytes(payload)
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    binding = ApplianceBoundaryBinding(
        policy_digest=digest,
        payload_digest="sha256:" + "a" * 64,
        raes_plan_digest="sha256:" + "c" * 64,
        raes_boundary_required=False,
        boundary_helper_image="example.test/aptl-boundary@sha256:" + "d" * 64,
        egress_proxy_image="example.test/aptl-egress@sha256:" + "e" * 64,
        boot_id="boot-42",
        guest_daemon_id="daemon-42",
        host_observation_id="host-42",
    )

    loaded = load_boundary_policy(policy_path, binding)

    assert loaded.policy_id == "participant-default"

    wrong = binding.model_copy(update={"policy_digest": "sha256:" + "b" * 64})
    with pytest.raises(ValueError, match="digest"):
        load_boundary_policy(policy_path, wrong)


@pytest.mark.parametrize(
    "authority",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "[::1]",
        "https://api.example.test",
        "*.example.test",
    ],
)
def test_egress_authority_rejects_literal_wildcard_and_url(authority: str) -> None:
    payload = _policy()
    payload["egress_authorities"] = [
        {
            "source": "egress",
            "authority": authority,
            "protocol": "tcp",
            "port": 443,
            "purpose": "model-provider",
            "resolution": "proxy-resolved-all-global",
            "failure_disposition": "deny",
        }
    ]

    with pytest.raises(ValidationError):
        ApplianceBoundaryPolicy.model_validate(payload)


def test_proxy_policy_is_a_narrow_projection_of_signed_authorities() -> None:
    policy = ApplianceBoundaryPolicy.model_validate(_policy())

    assert json.loads(render_egress_proxy_policy(policy)) == {
        "authorities": [
            {"authority": "api.example.test", "port": 443},
        ],
        "limits": {
            "max_connections": 32,
            "max_header_bytes": 4096,
            "header_timeout_seconds": 5,
            "connect_timeout_seconds": 10,
            "idle_timeout_seconds": 60,
        },
    }


def test_guest_publication_must_remain_loopback_only() -> None:
    payload = _policy()
    publication = payload["guest_publications"][0]
    publication["address"] = "0.0.0.0"

    with pytest.raises(ValidationError, match="loopback"):
        ApplianceBoundaryPolicy.model_validate(payload)


def test_proxy_policy_rejects_an_empty_authority_projection() -> None:
    payload = _policy()
    payload["egress_authorities"] = []
    policy = ApplianceBoundaryPolicy.model_validate(payload)

    with pytest.raises(ValueError, match="at least one"):
        render_egress_proxy_policy(policy)


def test_full_techvault_policy_is_distinct_seat_component_protection() -> None:
    policy = full_techvault_boundary_policy()

    assert policy.schema_version == "aptl.appliance-boundary/v3"
    assert policy.generation == 4
    assert policy.default_deny is True
    assert policy.internal_zone_isolation is False
    assert policy.seat_component_protection is True
    assert {item.component_class for item in policy.protected_components} == {
        "management-control",
        "evidence-capture",
        "evidence-store",
        "docker-authority",
        "credentials",
    }
    assert len({item.probe_identity for item in policy.protected_components}) == 5
    assert policy.permitted_host_flows == []


def test_seat_component_policy_rejects_incomplete_or_ambiguous_coverage() -> None:
    payload = full_techvault_boundary_policy().model_dump(mode="json")
    payload["protected_components"] = payload["protected_components"][:-1]

    with pytest.raises(ValidationError, match="protected component classes"):
        ApplianceBoundaryPolicy.model_validate(payload)

    payload = full_techvault_boundary_policy().model_dump(mode="json")
    payload["protected_components"][1]["probe_identity"] = payload[
        "protected_components"
    ][0]["probe_identity"]

    with pytest.raises(ValidationError, match="probe identities"):
        ApplianceBoundaryPolicy.model_validate(payload)

    payload = full_techvault_boundary_policy().model_dump(mode="json")
    payload["permitted_host_flows"] = [
        {
            "source": "ordinary-range-workload",
            "destination": "management-control",
            "protocol": "tcp",
            "ports": [8444, 8443],
            "purpose": "reviewed callback",
            "probe_identity": "reviewed-callback",
        }
    ]

    with pytest.raises(ValidationError, match="sorted unique"):
        ApplianceBoundaryPolicy.model_validate(payload)


def test_vm_only_policy_cannot_claim_seat_component_protection() -> None:
    payload = full_techvault_boundary_policy().model_dump(mode="json")
    payload["schema_version"] = "aptl.appliance-boundary/v2"
    payload["default_deny"] = False

    with pytest.raises(ValidationError, match="VM-only"):
        ApplianceBoundaryPolicy.model_validate(payload)


def test_boundary_binding_keeps_route_and_runtime_plan_identities_distinct() -> None:
    binding = ApplianceBoundaryBinding(
        policy_digest="sha256:" + "a" * 64,
        payload_digest="sha256:" + "b" * 64,
        participant_routes_digest="sha256:" + "c" * 64,
        raes_plan_digest=None,
        raes_boundary_required=False,
        boundary_helper_image="example.test/aptl-boundary@sha256:" + "d" * 64,
        egress_proxy_image="example.test/aptl-egress@sha256:" + "e" * 64,
        boot_id="boot-42",
        guest_daemon_id="daemon-42",
        host_observation_id="host-42",
    )

    assert binding.participant_routes_digest == "sha256:" + "c" * 64
    assert binding.raes_plan_digest is None

    conflated = binding.model_dump()
    conflated["raes_plan_digest"] = binding.participant_routes_digest
    with pytest.raises(ValidationError, match="different artifacts"):
        ApplianceBoundaryBinding.model_validate(conflated)
