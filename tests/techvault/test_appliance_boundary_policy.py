"""The canonical full-TechVault seat policy protects each seat component (#1700)."""

from aptl.appliance.policy import full_techvault_boundary_policy


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
