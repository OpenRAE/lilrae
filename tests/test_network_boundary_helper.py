"""Pure rendering checks for the authority-separated nftables helper."""

import importlib.util
import ipaddress
from pathlib import Path

import pytest


HELPER = (
    Path(__file__).parents[1] / "containers" / "network-boundary-helper" / "helper.py"
)


@pytest.fixture(scope="module")
def helper():
    spec = importlib.util.spec_from_file_location("network_boundary_helper", HELPER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _network(name: str, bridge: str, cidr: str) -> dict[str, object]:
    return {
        "name": name,
        "bridge": bridge,
        "ipv4_cidr": cidr,
        "ipv6_cidr": None,
        "ipv4_gateway": str(ipaddress.ip_network(cidr)[1]),
        "ipv6_gateway": None,
        "labels": [],
    }


def _raes_policy() -> dict[str, object]:
    return {
        "authority": "raes",
        "owner": "seat-17",
        "networks": [
            _network("orchard", "br-orchard", "10.44.1.0/24"),
            _network("quartz", "br-quartz", "10.44.2.0/24"),
        ],
        "owner_bindings": [
            {
                "owner_address": "provision.node.sentinel",
                "owner_resource_type": "node",
                "ipv4_by_network": [["quartz", "10.44.2.10"]],
                "ipv6_by_network": [],
            }
        ],
        "rules": [
            {
                "owner_address": "provision.node.sentinel",
                "owner_resource_type": "node",
                "owner_name": "sentinel",
                "name": "allow-web",
                "order": 0,
                "direction": "in",
                "from_network": "orchard",
                "to_network": "quartz",
                "protocol": "tcp",
                "ports": [443],
                "action": "allow",
            }
        ],
    }


def _platform_policy() -> dict[str, object]:
    return {
        "authority": "platform",
        "owner": "seat-17",
        "policy_digest": "sha256:" + "a" * 64,
        "networks": [
            _network("participant-net", "br-part", "10.50.1.0/24"),
            _network("management-net", "br-mgmt", "10.50.2.0/24"),
            _network("egress-net", "br-egress", "10.50.3.0/24"),
        ],
        "zone_networks": [
            {"zone": "participant", "network": "participant-net"},
            {"zone": "management", "network": "management-net"},
            {"zone": "egress", "network": "egress-net"},
        ],
        "anchors": [
            {
                "zone": "participant",
                "workload": {
                    "identity": "participant-gateway",
                    "labels": [["org.aptl.zone", "participant"]],
                    "ipv4_by_network": [["participant-net", "10.50.1.10"]],
                    "ipv6_by_network": [],
                },
            },
            {
                "zone": "management",
                "workload": {
                    "identity": "management-agent",
                    "labels": [["org.aptl.zone", "management"]],
                    "ipv4_by_network": [["management-net", "10.50.2.10"]],
                    "ipv6_by_network": [],
                },
            },
            {
                "zone": "egress",
                "workload": {
                    "identity": "egress-proxy",
                    "labels": [["org.aptl.zone", "egress"]],
                    "ipv4_by_network": [
                        ["management-net", "10.50.2.20"],
                        ["egress-net", "10.50.3.20"],
                    ],
                    "ipv6_by_network": [],
                },
            },
        ],
        "crossings": [
            {
                "source": "management",
                "destination": "egress",
                "protocol": "tcp",
                "ports": [3128],
                "purpose": "model-proxy",
            }
        ],
        "egress_ports": [443],
        "default_deny": True,
    }


def _seat_protection_policy() -> dict[str, object]:
    return {
        "authority": "seat-protection",
        "owner": "seat-17",
        "policy_digest": "sha256:" + "b" * 64,
        "networks": [
            _network("orchard", "br-orchard", "10.44.1.0/24"),
            {
                **_network("quartz", "br-quartz", "10.44.2.0/24"),
                "ipv6_cidr": "2001:db8:44::/64",
                "ipv6_gateway": "2001:db8:44::1",
            },
        ],
        "protected_components": [
            {
                "component_class": component_class,
                "probe_identity": "seat-" + component_class,
                "protocol": "tcp",
                "port": 43101 + index,
                "purpose": component_class + " boundary",
            }
            for index, component_class in enumerate(
                (
                    "management-control",
                    "evidence-capture",
                    "evidence-store",
                    "docker-authority",
                    "credentials",
                )
            )
        ],
        "permitted_flows": [
            {
                "source": "ordinary-range-workload",
                "destination": "management-control",
                "protocol": "tcp",
                "ports": [8443],
                "purpose": "reviewed management callback",
                "probe_identity": "reviewed-management-callback",
            }
        ],
        "default_deny": True,
    }


def _seat_observation(helper, family: str) -> dict[str, object]:
    ingress_key = "ibrname" if family == "bridge" else "iifname"
    table = helper._table_name("seat-17", "seat-protection")
    rules: list[dict[str, object]] = []
    network_gateways = {
        "br-orchard": (("ip", "10.44.1.1"),),
        "br-quartz": (("ip", "10.44.2.1"), ("ip6", "2001:db8:44::1")),
    }

    def interface_match(bridge: str) -> dict[str, object]:
        return {
            "match": {
                "op": "==",
                "left": {"meta": {"key": ingress_key}},
                "right": bridge,
            }
        }

    def add_rule(identity: str, expressions: list[dict[str, object]]) -> None:
        rules.append(
            {
                "rule": {
                    "family": family,
                    "table": table,
                    "chain": "host_input",
                    "expr": expressions,
                    "comment": helper._rule_marker(identity),
                }
            }
        )

    for bridge in network_gateways:
        add_rule(
            f"seat-protection/reply/{bridge}",
            [
                interface_match(bridge),
                {
                    "match": {
                        "op": "in",
                        "left": {"ct": {"key": "state"}},
                        "right": {"set": ["established", "related"]},
                    }
                },
                {"accept": None},
            ],
        )
    for bridge, gateways in network_gateways.items():
        for address_family, gateway in gateways:
            add_rule(
                "seat-protection/reviewed-management-callback/"
                f"{bridge}/{address_family}",
                [
                    interface_match(bridge),
                    {
                        "match": {
                            "op": "==",
                            "left": {
                                "payload": {
                                    "protocol": address_family,
                                    "field": "daddr",
                                }
                            },
                            "right": gateway,
                        }
                    },
                    {
                        "match": {
                            "op": "==",
                            "left": {
                                "payload": {
                                    "protocol": "tcp",
                                    "field": "dport",
                                }
                            },
                            "right": 8443,
                        }
                    },
                    {"accept": None},
                ],
            )
    for bridge in network_gateways:
        add_rule(
            f"seat-protection/default/{bridge}",
            [interface_match(bridge), {"drop": None}],
        )
    return {
        "nftables": [
            {
                "chain": {
                    "family": family,
                    "table": table,
                    "name": "host_input",
                    "type": "filter",
                    "hook": "input",
                    "prio": -300,
                    "policy": "accept",
                }
            },
            *rules,
        ]
    }


def test_raes_rules_remain_owner_anchored_and_separate(helper) -> None:
    rendered = helper.render_ruleset(_raes_policy(), existing_families=())

    assert "authority=raes" in rendered
    assert "policy-digest=" not in rendered
    assert "hook forward priority -200" in rendered
    assert 'iifname "br-orchard" oifname "br-quartz"' in rendered
    assert "ip daddr 10.44.2.10" in rendered
    assert "tcp dport 443 return" in rendered
    assert "ip daddr 10.44.2.10 jump owner_" in rendered


def test_platform_floor_covers_forward_and_guest_host_paths(helper) -> None:
    rendered = helper.render_ruleset(_platform_policy(), existing_families=())

    assert "authority=platform" in rendered
    assert "hook forward priority -300" in rendered
    assert "hook input priority -300" in rendered
    assert "hook output priority -300" in rendered
    assert 'iifname "br-mgmt" oifname "br-mgmt"' in rendered
    assert "ip saddr 10.50.2.10 ip daddr 10.50.2.20" in rendered
    assert "tcp dport 3128 accept" in rendered
    assert "tcp dport 443 accept" in rendered
    assert "ct state established,related accept" in rendered
    assert "ip daddr 10.50.3.20 ct state established,related accept" in rendered
    for bridge in ("br-part", "br-mgmt", "br-egress"):
        assert f'iifname "{bridge}" drop comment' in rendered
        assert f'oifname "{bridge}" drop comment' in rendered
    assert (
        "ip daddr { 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, "
        "127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, "
        "192.0.0.0/24, 192.168.0.0/16, 198.18.0.0/15, "
        "224.0.0.0/4, 240.0.0.0/4 } drop"
    ) in rendered


def test_seat_protection_filters_only_guest_input_for_every_range_bridge(
    helper,
) -> None:
    rendered = helper.render_ruleset(_seat_protection_policy(), existing_families=())

    assert "authority=seat-protection" in rendered
    assert "hook input priority -300" in rendered
    assert "hook forward" not in rendered
    assert "hook output" not in rendered
    assert "oifname" not in rendered
    assert "obrname" not in rendered
    assert "ct state established,related accept" in rendered
    assert "tcp dport 8443 accept" in rendered
    assert "ip daddr 10.44.1.1 tcp dport 8443 accept" in rendered
    assert "ip6 daddr 2001:db8:44::1 tcp dport 8443 accept" in rendered
    for bridge in ("br-orchard", "br-quartz"):
        assert f'iifname "{bridge}" drop comment' in rendered
        assert f'ibrname "{bridge}" drop comment' in rendered


def test_seat_protection_payload_is_closed_and_complete(helper) -> None:
    policy = _seat_protection_policy()
    policy["forward"] = True
    with pytest.raises(ValueError, match="fields"):
        helper.validate_policy(policy)

    policy = _seat_protection_policy()
    policy["protected_components"] = policy["protected_components"][:-1]
    with pytest.raises(ValueError, match="component classes"):
        helper.validate_policy(policy)

    policy = _seat_protection_policy()
    policy["networks"] = []
    with pytest.raises(ValueError, match="network"):
        helper.validate_policy(policy)

    policy = _seat_protection_policy()
    policy["networks"][0]["ipv4_gateway"] = None
    with pytest.raises(ValueError, match="gateway"):
        helper.validate_policy(policy)

    policy = _seat_protection_policy()
    policy["permitted_flows"][0]["ports"] = [8444, 8443]
    with pytest.raises(ValueError, match="semantics"):
        helper.validate_policy(policy)


@pytest.mark.parametrize("family", ["inet", "bridge"])
def test_seat_protection_readback_verifies_rule_expressions(
    helper, monkeypatch, family: str
) -> None:
    observed = _seat_observation(helper, family)
    monkeypatch.setattr(helper, "_table_payload", lambda *_: observed)

    assert helper._verify_observed_family(_seat_protection_policy(), family)

    default_rule = observed["nftables"][-1]["rule"]
    default_rule["expr"][-1] = {"accept": None}

    assert not helper._verify_observed_family(_seat_protection_policy(), family)

    reordered = _seat_observation(helper, family)
    reordered["nftables"][1], reordered["nftables"][-1] = (
        reordered["nftables"][-1],
        reordered["nftables"][1],
    )
    monkeypatch.setattr(helper, "_table_payload", lambda *_: reordered)

    assert not helper._verify_observed_family(_seat_protection_policy(), family)


def test_platform_bootstrap_is_deny_only_before_anchors_exist(helper) -> None:
    policy = _platform_policy()
    policy["bootstrap"] = True
    policy["anchors"] = []
    policy["crossings"] = []
    policy["egress_ports"] = []

    rendered = helper.render_ruleset(policy, existing_families=())

    assert "authority=platform" in rendered
    assert 'iifname "br-mgmt" drop comment' in rendered
    assert 'oifname "br-mgmt" drop comment' in rendered
    assert "tcp dport" not in rendered
    assert "ip saddr" not in rendered


def test_platform_bootstrap_refuses_grants_without_observed_anchors(helper) -> None:
    policy = _platform_policy()
    policy["bootstrap"] = True
    policy["anchors"] = []

    with pytest.raises(ValueError, match="bootstrap"):
        helper.validate_policy(policy)


def test_authorities_get_distinct_owned_tables(helper) -> None:
    raes = helper.render_ruleset(_raes_policy(), existing_families=())
    platform = helper.render_ruleset(_platform_policy(), existing_families=())

    raes_table = next(
        line for line in raes.splitlines() if line.startswith("table inet")
    )
    platform_table = next(
        line for line in platform.splitlines() if line.startswith("table inet")
    )
    assert raes_table != platform_table


def test_helper_rejects_cross_authority_fields(helper) -> None:
    policy = _raes_policy()
    policy["default_deny"] = True

    with pytest.raises(ValueError):
        helper.validate_policy(policy)


def test_multiple_acl_owners_remain_independent_intersecting_chains(helper) -> None:
    policy = _raes_policy()
    policy["owner_bindings"].append(
        {
            "owner_address": "provision.node.gateway",
            "owner_resource_type": "node",
            "ipv4_by_network": [["orchard", "10.44.1.10"]],
            "ipv6_by_network": [],
        }
    )
    policy["rules"].append(
        {
            "owner_address": "provision.node.gateway",
            "owner_resource_type": "node",
            "owner_name": "gateway",
            "name": "deny-other",
            "order": 0,
            "direction": "out",
            "from_network": "orchard",
            "to_network": "quartz",
            "protocol": "any",
            "ports": [],
            "action": "deny",
        }
    )
    policy["owner_bindings"].sort(key=lambda item: item["owner_address"])
    policy["rules"].sort(
        key=lambda item: (item["owner_address"], item["order"], item["name"])
    )

    rendered = helper.render_ruleset(policy, existing_families=())

    assert rendered.count("chain owner_") == 4
    assert "ip daddr 10.44.2.10 jump owner_" in rendered
    assert "ip saddr 10.44.1.10 jump owner_" in rendered
    assert "drop comment" in rendered


def test_helper_rejects_malformed_direct_acl_without_native_mutation(helper) -> None:
    policy = _raes_policy()
    policy["rules"][0]["from_network"] = ["orchard"]

    with pytest.raises(ValueError, match="endpoint"):
        helper.validate_policy(policy)


def test_authored_wildcard_endpoint_is_scoped_by_acl_owner(helper) -> None:
    policy = _raes_policy()
    policy["rules"][0]["from_network"] = None

    rendered = helper.render_ruleset(policy, existing_families=())

    assert "ip daddr 10.44.2.10 tcp dport 443 return" in rendered


@pytest.mark.parametrize(
    ("direction", "protocol", "needle"),
    [
        ("out", "udp", "udp dport 443 return"),
        ("inout", "icmp", "meta l4proto icmp return"),
        ("in", "any", "ip daddr 10.44.2.10 return"),
    ],
)
def test_supported_acl_direction_and_protocol_subset_is_rendered_exactly(
    helper,
    direction: str,
    protocol: str,
    needle: str,
) -> None:
    policy = _raes_policy()
    rule = policy["rules"][0]
    policy["owner_bindings"][0]["ipv4_by_network"].append(["orchard", "10.44.1.20"])
    rule["direction"] = direction
    rule["protocol"] = protocol
    rule["ports"] = [443] if protocol in {"tcp", "udp"} else []

    rendered = helper.render_ruleset(policy, existing_families=())

    assert needle in rendered
    if direction == "inout":
        assert rendered.count("meta l4proto icmp return") == 4


def test_ruleset_replacement_is_one_atomic_native_transaction(helper) -> None:
    rendered = helper.render_ruleset(
        _raes_policy(),
        existing_families=("bridge", "inet"),
    )

    assert rendered.startswith("delete table inet ")
    assert "\ndelete table bridge " in rendered
    assert rendered.count("table inet ") == 2
    assert rendered.count("table bridge ") == 2
