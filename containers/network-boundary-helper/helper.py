#!/usr/bin/env python3
"""Closed nftables apply/observe/cleanup helper for one boundary authority."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence

_TOKEN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,159}$")
_BRIDGE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,14}$")
_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
_ACTIONS = frozenset({"allow", "deny"})
_PROTOCOLS = frozenset({"any", "tcp", "udp", "icmp"})
_DIRECTIONS = frozenset({"in", "out", "inout"})
_ZONES = frozenset({"participant", "management", "egress"})
_PROTECTED_COMPONENTS = frozenset(
    {
        "management-control",
        "evidence-capture",
        "evidence-store",
        "docker-authority",
        "credentials",
    }
)
_EGRESS_DENIED_IPV4 = (
    "0.0.0.0/8",
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.0.0.0/24",
    "192.168.0.0/16",
    "198.18.0.0/15",
    "224.0.0.0/4",
    "240.0.0.0/4",
)


def _canonical(policy: Mapping[str, object]) -> str:
    return json.dumps(policy, sort_keys=True, separators=(",", ":"))


def _digest(policy: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(_canonical(policy).encode()).hexdigest()


def _table_name(owner: str, authority: str) -> str:
    suffix = hashlib.sha256(f"{owner}:{authority}".encode()).hexdigest()[:12]
    return f"aptl_bnd_{suffix}"


def _owner_marker(owner: str) -> str:
    return hashlib.sha256(owner.encode()).hexdigest()[:16]


def _rule_marker(identity: str) -> str:
    return "aptl-rule=" + hashlib.sha256(identity.encode()).hexdigest()[:24]


def _raes_owner_chain(owner_address: str) -> str:
    return "owner_" + hashlib.sha256(owner_address.encode()).hexdigest()[:12]


def _quoted(value: str) -> str:
    return json.dumps(value)


def validate_policy(policy: object) -> dict[str, object]:
    """Validate one closed authority payload before rendering native syntax."""

    if not isinstance(policy, dict):
        raise ValueError("policy must be an object")
    authority = policy.get("authority")
    if authority == "raes":
        return _validate_raes(policy)
    if authority == "platform":
        return _validate_platform(policy)
    if authority == "seat-protection":
        return _validate_seat_protection(policy)
    if authority == "native-range":
        return _validate_native_range(policy)
    raise ValueError("policy authority is invalid")


def _validate_native_range(policy: dict[str, object]) -> dict[str, object]:
    _validate_common(policy, {"authority", "owner", "networks", "allowances"})
    networks = policy["networks"]
    allowances = policy["allowances"]
    if (
        not isinstance(networks, list)
        or not networks
        or not isinstance(allowances, list)
    ):
        raise ValueError("native range collections are invalid")
    index = _validated_network_index(networks, authority="native-range")
    if len({n["bridge"] for n in index.values()}) != len(index):
        raise ValueError("native range bridges must be unique")
    for allowance in allowances:
        if not isinstance(allowance, dict) or set(allowance) != {
            "destination",
            "protocol",
            "port",
        }:
            raise ValueError("native range allowance is invalid")
        address = ipaddress.ip_address(allowance["destination"])
        if address.is_loopback or address.is_multicast or address.is_unspecified:
            raise ValueError("native range allowance must be unicast")
        if allowance["protocol"] not in {"tcp", "udp"}:
            raise ValueError("native range allowance protocol is invalid")
        _validate_ports([allowance["port"]], allowance["protocol"], required=True)
    return policy


def _validate_common(policy: Mapping[str, object], fields: set[str]) -> None:
    if set(policy) != fields:
        raise ValueError("policy fields are invalid")
    owner = policy.get("owner")
    if not isinstance(owner, str) or not _TOKEN.fullmatch(owner):
        raise ValueError("owner is invalid")


def _validate_network(network: object) -> dict[str, object]:
    fields = {
        "name",
        "bridge",
        "ipv4_cidr",
        "ipv6_cidr",
        "ipv4_gateway",
        "ipv6_gateway",
        "labels",
    }
    if not isinstance(network, dict) or set(network) != fields:
        raise ValueError("network is invalid")
    name = network["name"]
    bridge = network["bridge"]
    labels = network["labels"]
    if (
        not isinstance(name, str)
        or not _TOKEN.fullmatch(name)
        or not isinstance(bridge, str)
        or not _BRIDGE.fullmatch(bridge)
        or not isinstance(labels, list)
    ):
        raise ValueError("network identity is invalid")
    for key, version in (("ipv4_cidr", 4), ("ipv6_cidr", 6)):
        value = network[key]
        if value is not None:
            if not isinstance(value, str):
                raise ValueError("network CIDR is invalid")
            if ipaddress.ip_network(value, strict=False).version != version:
                raise ValueError("network CIDR family is invalid")
    for key, cidr_key, version in (
        ("ipv4_gateway", "ipv4_cidr", 4),
        ("ipv6_gateway", "ipv6_cidr", 6),
    ):
        gateway = network[key]
        cidr = network[cidr_key]
        if gateway is not None:
            if (
                not isinstance(gateway, str)
                or not isinstance(cidr, str)
                or ipaddress.ip_address(gateway).version != version
                or ipaddress.ip_address(gateway)
                not in ipaddress.ip_network(cidr, strict=False)
            ):
                raise ValueError("network gateway is invalid")
    _validate_labels(labels)
    return network


def _validate_labels(labels: object) -> None:
    if (
        not isinstance(labels, list)
        or any(
            not isinstance(item, list)
            or len(item) != 2
            or not all(isinstance(value, str) for value in item)
            for item in labels
        )
        or labels != sorted(labels)
        or len({item[0] for item in labels}) != len(labels)
    ):
        raise ValueError("network labels are invalid")


def _validate_raes(policy: dict[str, object]) -> dict[str, object]:
    _validate_common(
        policy,
        {"authority", "owner", "networks", "owner_bindings", "rules"},
    )
    networks = policy["networks"]
    bindings = policy["owner_bindings"]
    rules = policy["rules"]
    if not all(isinstance(value, list) for value in (networks, bindings, rules)):
        raise ValueError("RAES policy collections must be lists")
    network_index = _validated_network_index(networks, authority="RAES")
    if any(network["ipv6_cidr"] is not None for network in network_index.values()):
        raise ValueError("RAES ACL networks must remain IPv4-only")
    binding_index: dict[str, dict[str, object]] = {}
    for binding in bindings:
        _validate_raes_binding(binding, network_index, binding_index)
    prior: tuple[str, int, str] | None = None
    seen_orders: set[tuple[str, int]] = set()
    seen_names: set[tuple[str, str]] = set()
    for rule in rules:
        current = _validate_raes_rule(
            rule,
            binding_index,
            network_index,
            seen_orders,
            seen_names,
        )
        if prior is not None and current < prior:
            raise ValueError("RAES rules are not deterministically ordered")
        prior = current
    return policy


def _validated_network_index(
    networks: Sequence[object],
    *,
    authority: str,
) -> dict[str, dict[str, object]]:
    index: dict[str, dict[str, object]] = {}
    for network in networks:
        validated = _validate_network(network)
        name = str(validated["name"])
        if name in index:
            raise ValueError(f"{authority} network identities must be unique")
        index[name] = validated
    return index


def _validate_address_pairs(
    pairs: object,
    family_key: str,
    version: int,
    networks: Mapping[str, Mapping[str, object]],
) -> None:
    if not isinstance(pairs, list):
        raise ValueError("boundary owner addresses are invalid")
    seen_networks: set[str] = set()
    for pair in pairs:
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or not isinstance(pair[0], str)
            or pair[0] not in networks
            or not isinstance(pair[1], str)
            or pair[0] in seen_networks
        ):
            raise ValueError("boundary owner address is invalid")
        parsed = ipaddress.ip_address(pair[1])
        cidr = networks[pair[0]][family_key.replace("_by_network", "_cidr")]
        if (
            parsed.version != version
            or not isinstance(cidr, str)
            or parsed not in ipaddress.ip_network(cidr, strict=False)
        ):
            raise ValueError("boundary owner address is outside its network")
        seen_networks.add(pair[0])


def _validate_raes_binding(
    binding: object,
    networks: Mapping[str, Mapping[str, object]],
    index: dict[str, dict[str, object]],
) -> None:
    if not isinstance(binding, dict) or set(binding) != {
        "owner_address",
        "owner_resource_type",
        "ipv4_by_network",
        "ipv6_by_network",
    }:
        raise ValueError("RAES owner binding is invalid")
    owner = binding["owner_address"]
    kind = binding["owner_resource_type"]
    if (
        not isinstance(owner, str)
        or not _TOKEN.fullmatch(owner)
        or not isinstance(kind, str)
        or kind not in {"node", "network"}
        or owner in index
    ):
        raise ValueError("RAES owner identity is invalid")
    _validate_address_pairs(binding["ipv4_by_network"], "ipv4_by_network", 4, networks)
    _validate_address_pairs(binding["ipv6_by_network"], "ipv6_by_network", 6, networks)
    if binding["ipv6_by_network"]:
        raise ValueError("RAES ACL owner addresses must remain IPv4-only")
    if kind == "node" and not (
        binding["ipv4_by_network"] or binding["ipv6_by_network"]
    ):
        raise ValueError("RAES node owner has no exact address")
    index[owner] = binding


def _validate_raes_rule(
    rule: object,
    bindings: Mapping[str, Mapping[str, object]],
    networks: Mapping[str, Mapping[str, object]],
    seen_orders: set[tuple[str, int]],
    seen_names: set[tuple[str, str]],
) -> tuple[str, int, str]:
    fields = {
        "owner_address",
        "owner_resource_type",
        "owner_name",
        "name",
        "order",
        "direction",
        "from_network",
        "to_network",
        "protocol",
        "ports",
        "action",
    }
    if not isinstance(rule, dict) or set(rule) != fields:
        raise ValueError("RAES rule is invalid")
    owner = rule["owner_address"]
    binding = bindings.get(owner) if isinstance(owner, str) else None
    if binding is None or binding["owner_resource_type"] != rule["owner_resource_type"]:
        raise ValueError("RAES rule owner is invalid")
    _validate_raes_rule_semantics(rule, binding, networks)
    identity = str(rule["name"])
    order = int(rule["order"])
    order_key = (owner, order)
    name_key = (owner, identity)
    if order_key in seen_orders or name_key in seen_names:
        raise ValueError("RAES rule identity is not unique")
    seen_orders.add(order_key)
    seen_names.add(name_key)
    return owner, order, identity


def _validate_raes_rule_semantics(
    rule: Mapping[str, object],
    binding: Mapping[str, object],
    networks: Mapping[str, Mapping[str, object]],
) -> None:
    direction = rule["direction"]
    protocol = rule["protocol"]
    action = rule["action"]
    owner_name = rule["owner_name"]
    identity = rule["name"]
    order = rule["order"]
    if not isinstance(direction, str) or direction not in _DIRECTIONS:
        raise ValueError("RAES rule direction is invalid")
    if (
        not isinstance(protocol, str)
        or protocol not in _PROTOCOLS
        or not isinstance(action, str)
        or action not in _ACTIONS
    ):
        raise ValueError("RAES rule semantics are invalid")
    if any(
        rule[endpoint] is not None
        and (not isinstance(rule[endpoint], str) or rule[endpoint] not in networks)
        for endpoint in ("from_network", "to_network")
    ):
        raise ValueError("RAES rule endpoint is invalid")
    _validate_ports(rule["ports"], protocol)
    if (
        not isinstance(identity, str)
        or not _TOKEN.fullmatch(identity)
        or not isinstance(owner_name, str)
        or not _TOKEN.fullmatch(owner_name)
        or not isinstance(order, int)
        or isinstance(order, bool)
        or order < 0
    ):
        raise ValueError("RAES rule ordering is invalid")
    if binding["owner_resource_type"] == "network" and owner_name not in networks:
        raise ValueError("RAES network owner is unresolved")


def _validate_platform(policy: dict[str, object]) -> dict[str, object]:
    bootstrap = policy.get("bootstrap") is True
    _validate_common(
        policy,
        {
            "authority",
            "owner",
            "policy_digest",
            "networks",
            "zone_networks",
            "anchors",
            "crossings",
            "egress_ports",
            "default_deny",
            *({"bootstrap"} if bootstrap else set()),
        },
    )
    if not isinstance(policy["policy_digest"], str) or not _DIGEST.fullmatch(
        policy["policy_digest"]
    ):
        raise ValueError("platform policy digest is invalid")
    if policy["default_deny"] is not True:
        raise ValueError("platform policy must be default deny")
    anchors = policy["anchors"]
    zone_networks = policy["zone_networks"]
    crossings = policy["crossings"]
    networks = policy["networks"]
    egress_ports = policy["egress_ports"]
    if (
        not isinstance(anchors, list)
        or not isinstance(zone_networks, list)
        or not isinstance(crossings, list)
        or not isinstance(networks, list)
    ):
        raise ValueError("platform policy collections must be lists")
    network_index = _validated_platform_networks(networks)
    _validate_ports(egress_ports, "tcp")
    zone_network_index = _validated_zone_networks(zone_networks, network_index)
    if bootstrap:
        if anchors or crossings or egress_ports:
            raise ValueError("platform bootstrap cannot grant traffic")
        return policy
    zones: set[str] = set()
    for anchor in anchors:
        zones.add(
            _validate_platform_anchor(
                anchor,
                networks=network_index,
                zone_networks=zone_network_index,
                seen=zones,
            )
        )
    if zones != _ZONES:
        raise ValueError("platform zones are incomplete")
    for crossing in crossings:
        _validate_platform_crossing(crossing, zones)
    return policy


def _validate_seat_protection(policy: dict[str, object]) -> dict[str, object]:
    """Validate the closed input-only protected-seat authority."""

    _validate_common(
        policy,
        {
            "authority",
            "owner",
            "policy_digest",
            "networks",
            "protected_components",
            "permitted_flows",
            "default_deny",
        },
    )
    digest = policy["policy_digest"]
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        raise ValueError("protected-seat policy digest is invalid")
    if policy["default_deny"] is not True:
        raise ValueError("protected-seat policy must be default deny")
    networks = policy["networks"]
    components = policy["protected_components"]
    flows = policy["permitted_flows"]
    if not all(isinstance(value, list) for value in (networks, components, flows)):
        raise ValueError("protected-seat policy collections must be lists")
    if not networks:
        raise ValueError("protected-seat network binding is required")
    network_index = _validated_network_index(networks, authority="protected-seat")
    bridges = [str(network["bridge"]) for network in network_index.values()]
    if len(bridges) != len(set(bridges)) or any(
        network["ipv4_cidr"] is None and network["ipv6_cidr"] is None
        for network in network_index.values()
    ):
        raise ValueError("protected-seat network identity is invalid")
    if any(
        (network["ipv4_cidr"] is not None and network["ipv4_gateway"] is None)
        or (network["ipv6_cidr"] is not None and network["ipv6_gateway"] is None)
        for network in network_index.values()
    ):
        raise ValueError("protected-seat network gateway is missing")
    classes: set[str] = set()
    probe_ids: set[str] = set()
    for component in components:
        _validate_protected_component(component, classes, probe_ids)
    if classes != _PROTECTED_COMPONENTS:
        raise ValueError("protected component classes are incomplete")
    for flow in flows:
        _validate_permitted_host_flow(flow, classes, probe_ids)
    return policy


def _validate_protected_component(
    component: object,
    classes: set[str],
    probe_ids: set[str],
) -> None:
    fields = {"component_class", "probe_identity", "protocol", "port", "purpose"}
    if not isinstance(component, dict) or set(component) != fields:
        raise ValueError("protected component is invalid")
    component_class = component["component_class"]
    probe_identity = component["probe_identity"]
    protocol = component["protocol"]
    port = component["port"]
    purpose = component["purpose"]
    if (
        not isinstance(component_class, str)
        or component_class not in _PROTECTED_COMPONENTS
        or component_class in classes
        or not isinstance(probe_identity, str)
        or not _TOKEN.fullmatch(probe_identity)
        or probe_identity in probe_ids
        or not isinstance(protocol, str)
        or protocol not in {"tcp", "udp"}
        or not isinstance(port, int)
        or isinstance(port, bool)
        or not 0 < port <= 65535
        or not isinstance(purpose, str)
        or not purpose
    ):
        raise ValueError("protected component semantics are invalid")
    classes.add(component_class)
    probe_ids.add(probe_identity)


def _validate_permitted_host_flow(
    flow: object,
    classes: set[str],
    probe_ids: set[str],
) -> None:
    fields = {
        "source",
        "destination",
        "protocol",
        "ports",
        "purpose",
        "probe_identity",
    }
    if not isinstance(flow, dict) or set(flow) != fields:
        raise ValueError("protected-seat flow is invalid")
    source = flow["source"]
    destination = flow["destination"]
    protocol = flow["protocol"]
    purpose = flow["purpose"]
    probe_identity = flow["probe_identity"]
    ports = flow["ports"]
    if (
        source != "ordinary-range-workload"
        or not isinstance(destination, str)
        or destination not in classes
        or not isinstance(protocol, str)
        or protocol not in {"tcp", "udp"}
        or not isinstance(purpose, str)
        or not purpose
        or not isinstance(probe_identity, str)
        or not _TOKEN.fullmatch(probe_identity)
        or probe_identity in probe_ids
        or not isinstance(ports, list)
        or ports != sorted(ports)
        or len(ports) != len(set(ports))
    ):
        raise ValueError("protected-seat flow semantics are invalid")
    _validate_ports(ports, protocol, required=True)
    probe_ids.add(probe_identity)


def _validated_platform_networks(
    networks: Sequence[object],
) -> dict[str, dict[str, object]]:
    index = _validated_network_index(networks, authority="platform")
    if len(index) != 3 or any(
        network["ipv6_cidr"] is not None for network in index.values()
    ):
        raise ValueError("platform requires three IPv4-only networks")
    return index


def _validated_zone_networks(
    values: Sequence[object],
    networks: Mapping[str, object],
) -> dict[str, str]:
    index: dict[str, str] = {}
    for item in values:
        if not isinstance(item, dict) or set(item) != {"zone", "network"}:
            raise ValueError("platform zone network is invalid")
        zone = item["zone"]
        network = item["network"]
        if (
            not isinstance(zone, str)
            or not isinstance(network, str)
            or zone not in _ZONES
            or zone in index
            or network not in networks
        ):
            raise ValueError("platform zone network is invalid")
        index[zone] = network
    if set(index) != _ZONES or set(index.values()) != set(networks):
        raise ValueError("platform zone networks must be exact and distinct")
    return index


def _validate_platform_anchor(
    anchor: object,
    *,
    networks: Mapping[str, Mapping[str, object]],
    zone_networks: Mapping[str, str],
    seen: set[str],
) -> str:
    if not isinstance(anchor, dict) or set(anchor) != {"zone", "workload"}:
        raise ValueError("platform anchor is invalid")
    zone = anchor["zone"]
    if not isinstance(zone, str) or zone not in _ZONES or zone in seen:
        raise ValueError("platform anchor is invalid")
    workload = anchor["workload"]
    fields = {"identity", "labels", "ipv4_by_network", "ipv6_by_network"}
    if not isinstance(workload, dict) or set(workload) != fields:
        raise ValueError("platform workload is invalid")
    _validate_labels(workload["labels"])
    identity = workload["identity"]
    if not isinstance(identity, str) or not _TOKEN.fullmatch(identity):
        raise ValueError("platform workload identity is invalid")
    ipv4 = workload["ipv4_by_network"]
    if not isinstance(ipv4, list) or not ipv4 or workload["ipv6_by_network"] != []:
        raise ValueError("platform workload must have an IPv4 attachment")
    _validate_address_pairs(ipv4, "ipv4_by_network", 4, networks)
    _validate_address_pairs(workload["ipv6_by_network"], "ipv6_by_network", 6, networks)
    attached = {
        str(pair[0]) for pair in ipv4 if isinstance(pair, list) and len(pair) == 2
    }
    if zone_networks[zone] not in attached:
        raise ValueError("platform anchor is absent from its policy network")
    return zone


def _validate_platform_crossing(
    crossing: object,
    zones: set[str],
) -> None:
    fields = {"source", "destination", "protocol", "ports", "purpose"}
    if not isinstance(crossing, dict) or set(crossing) != fields:
        raise ValueError("platform crossing is invalid")
    source = crossing["source"]
    destination = crossing["destination"]
    protocol = crossing["protocol"]
    purpose = crossing["purpose"]
    if (
        not isinstance(source, str)
        or not isinstance(destination, str)
        or not isinstance(protocol, str)
        or source not in zones
        or destination not in zones
        or protocol not in {"tcp", "udp"}
        or not isinstance(purpose, str)
        or not purpose
    ):
        raise ValueError("platform crossing semantics are invalid")
    _validate_ports(crossing["ports"], protocol, required=True)


def _validate_ports(value: object, protocol: str, *, required: bool = False) -> None:
    if (
        not isinstance(value, list)
        or (required and not value)
        or any(
            not isinstance(port, int) or isinstance(port, bool) or not 0 < port <= 65535
            for port in value
        )
        or (value and protocol not in {"tcp", "udp"})
    ):
        raise ValueError("ports are invalid")


def _network_index(policy: Mapping[str, object]) -> dict[str, dict[str, object]]:
    networks = policy["networks"]
    assert isinstance(networks, list)
    return {
        str(network["name"]): network
        for network in networks
        if isinstance(network, dict)
    }


def _transport(rule: Mapping[str, object]) -> str:
    protocol = str(rule["protocol"])
    if protocol in {"tcp", "udp"}:
        ports = rule["ports"]
        if isinstance(ports, list) and ports:
            rendered = (
                str(ports[0])
                if len(ports) == 1
                else "{ " + ", ".join(str(port) for port in ports) + " }"
            )
            return f"{protocol} dport {rendered}"
        # A bare protocol keyword is not nftables syntax; match every port.
        return f"meta l4proto {protocol}"
    if protocol == "icmp":
        return "meta l4proto icmp"
    return ""


def _interface_expression(
    source: str | None,
    destination: str | None,
    networks: Mapping[str, Mapping[str, object]],
    *,
    family: str,
) -> list[str]:
    parts: list[str] = []
    ingress = "ibrname" if family == "bridge" else "iifname"
    egress = "obrname" if family == "bridge" else "oifname"
    if source is not None:
        parts.extend([ingress, _quoted(str(networks[source]["bridge"]))])
    if destination is not None:
        parts.extend([egress, _quoted(str(networks[destination]["bridge"]))])
    return parts


def _address_expression(
    source: str | None,
    destination: str | None,
    networks: Mapping[str, Mapping[str, object]],
) -> list[str]:
    parts: list[str] = []
    for reference, direction in ((source, "saddr"), (destination, "daddr")):
        if reference is None:
            continue
        network = networks[reference]
        cidr = network.get("ipv4_cidr")
        if isinstance(cidr, str):
            parts.extend(["ip", direction, cidr])
    return parts


def _binding_addresses(binding: Mapping[str, object], network: str | None) -> list[str]:
    pairs = binding["ipv4_by_network"]
    assert isinstance(pairs, list)
    return [
        str(pair[1])
        for pair in pairs
        if isinstance(pair, list) and (network is None or pair[0] == network)
    ]


def _raes_rule_expressions(
    policy: Mapping[str, object],
    rule: Mapping[str, object],
    *,
    family: str,
) -> list[str]:
    networks = _network_index(policy)
    bindings = policy["owner_bindings"]
    assert isinstance(bindings, list)
    binding = next(
        item
        for item in bindings
        if isinstance(item, dict) and item["owner_address"] == rule["owner_address"]
    )
    directions = (
        ("in", "out") if rule["direction"] == "inout" else (str(rule["direction"]),)
    )
    expressions: list[str] = []
    for direction in directions:
        source = rule["from_network"]
        destination = rule["to_network"]
        source_ref = source if isinstance(source, str) else None
        destination_ref = destination if isinstance(destination, str) else None
        parts = _interface_expression(
            source_ref, destination_ref, networks, family=family
        )
        if family == "inet":
            parts.extend(_address_expression(source_ref, destination_ref, networks))
        if binding["owner_resource_type"] == "network":
            owner_name = str(rule["owner_name"])
            if direction == "in":
                parts.extend(
                    _interface_expression(None, owner_name, networks, family=family)
                )
            else:
                parts.extend(
                    _interface_expression(owner_name, None, networks, family=family)
                )
        else:
            owner_network = destination_ref if direction == "in" else source_ref
            addresses = _binding_addresses(binding, owner_network)
            if not addresses:
                raise ValueError("node ACL owner has no exact address")
            rendered = (
                addresses[0]
                if len(addresses) == 1
                else "{ " + ", ".join(addresses) + " }"
            )
            parts.extend(["ip", "daddr" if direction == "in" else "saddr", rendered])
        transport = _transport(rule)
        if transport:
            parts.append(transport)
        parts.append("return" if rule["action"] == "allow" else "drop")
        identity = f"{rule['owner_address']}/{rule['name']}/{direction}"
        parts.extend(["comment", _quoted(_rule_marker(identity))])
        expressions.append("    " + " ".join(parts))
    return expressions


def _raes_table(
    policy: Mapping[str, object], family: str, table_name: str
) -> list[str]:
    owner = str(policy["owner"])
    digest = _digest(policy)
    bindings = policy["owner_bindings"]
    rules = policy["rules"]
    assert isinstance(bindings, list)
    assert isinstance(rules, list)
    lines = [
        f"table {family} {table_name} {{",
        (
            "  comment "
            + _quoted(
                f"aptl-owner={_owner_marker(owner)},authority=raes,digest={digest}"
            )
        ),
    ]
    chain_by_owner: dict[str, str] = {}
    for binding in bindings:
        if not isinstance(binding, Mapping):
            continue
        owner_address = str(binding["owner_address"])
        chain = _raes_owner_chain(owner_address)
        chain_by_owner[owner_address] = chain
        lines.append(f"  chain {chain} {{")
        for rule in rules:
            if isinstance(rule, Mapping) and rule["owner_address"] == owner_address:
                lines.extend(_raes_rule_expressions(policy, rule, family=family))
        lines.extend(
            [
                (
                    "    return comment "
                    + _quoted(_rule_marker(f"{owner_address}/default"))
                ),
                "  }",
            ]
        )
    lines.extend(
        [
            "  chain forward {",
            "    type filter hook forward priority -200; policy accept;",
        ]
    )
    networks = _network_index(policy)
    for binding in bindings:
        if not isinstance(binding, Mapping):
            continue
        owner_address = str(binding["owner_address"])
        chain = chain_by_owner[owner_address]
        if binding["owner_resource_type"] == "node":
            addresses = _binding_addresses(binding, None)
            rendered = (
                addresses[0]
                if len(addresses) == 1
                else "{ " + ", ".join(addresses) + " }"
            )
            lines.append(
                f"    ip daddr {rendered} jump {chain} comment "
                + _quoted(_rule_marker(f"{owner_address}/dispatch/in"))
            )
            lines.append(
                f"    ip saddr {rendered} jump {chain} comment "
                + _quoted(_rule_marker(f"{owner_address}/dispatch/out"))
            )
        else:
            owner_rules = [
                rule
                for rule in rules
                if isinstance(rule, Mapping) and rule["owner_address"] == owner_address
            ]
            owner_names = {str(rule["owner_name"]) for rule in owner_rules}
            for owner_name in sorted(owner_names):
                bridge = str(networks[owner_name]["bridge"])
                ingress = "ibrname" if family == "bridge" else "iifname"
                egress = "obrname" if family == "bridge" else "oifname"
                lines.append(
                    f"    {egress} {_quoted(bridge)} jump {chain} comment "
                    + _quoted(_rule_marker(f"{owner_address}/dispatch/in"))
                )
                lines.append(
                    f"    {ingress} {_quoted(bridge)} jump {chain} comment "
                    + _quoted(_rule_marker(f"{owner_address}/dispatch/out"))
                )
    lines.extend(["  }", "}"])
    return lines


def _platform_index(
    policy: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    anchors = policy["anchors"]
    assert isinstance(anchors, list)
    return {
        str(anchor["zone"]): anchor["workload"]
        for anchor in anchors
        if isinstance(anchor, dict) and isinstance(anchor["workload"], dict)
    }


def _workload_ipv4(workload: Mapping[str, object]) -> dict[str, str]:
    pairs = workload["ipv4_by_network"]
    assert isinstance(pairs, list)
    return {
        str(pair[0]): str(pair[1])
        for pair in pairs
        if isinstance(pair, list) and len(pair) == 2
    }


def _platform_table(
    policy: Mapping[str, object], family: str, table_name: str
) -> list[str]:
    owner = str(policy["owner"])
    digest = _digest(policy)
    anchors = _platform_index(policy)
    networks = _network_index(policy)
    lines = [
        f"table {family} {table_name} {{",
        (
            "  comment "
            + _quoted(
                f"aptl-owner={_owner_marker(owner)},authority=platform,digest={digest}"
            )
        ),
        "  chain forward {",
        "    type filter hook forward priority -300; policy accept;",
    ]
    crossings = policy["crossings"]
    assert isinstance(crossings, list)
    if family == "bridge":
        for bridge in sorted(str(item["bridge"]) for item in networks.values()):
            # Link-local address resolution is not an inter-zone grant. Without
            # these bounded L2 control frames, an otherwise-authorized IP flow
            # depends on a stale neighbor cache and fails after a clean boot.
            lines.append(
                f"    ibrname {_quoted(bridge)} obrname {_quoted(bridge)} "
                'ether type arp accept comment "platform/arp"'
            )
            lines.append(
                f"    ibrname {_quoted(bridge)} obrname {_quoted(bridge)} "
                "ether type ip6 meta l4proto ipv6-icmp "
                "icmpv6 type { nd-neighbor-solicit, nd-neighbor-advert } "
                'accept comment "platform/nd"'
            )
    for crossing in crossings:
        if not isinstance(crossing, Mapping):
            continue
        source_addresses = _workload_ipv4(anchors[str(crossing["source"])])
        destination_addresses = _workload_ipv4(anchors[str(crossing["destination"])])
        ingress = "ibrname" if family == "bridge" else "iifname"
        egress = "obrname" if family == "bridge" else "oifname"
        ports = crossing["ports"]
        assert isinstance(ports, list)
        rendered_ports = (
            str(ports[0])
            if len(ports) == 1
            else "{ " + ", ".join(str(port) for port in ports) + " }"
        )
        identity = f"platform/{crossing['purpose']}"
        for network_name in sorted(set(source_addresses) & set(destination_addresses)):
            bridge = str(networks[network_name]["bridge"])
            source = source_addresses[network_name]
            destination = destination_addresses[network_name]
            lines.append(
                f"    {ingress} {_quoted(bridge)} {egress} {_quoted(bridge)} "
                f"ip saddr {source} ip daddr {destination} "
                f"{crossing['protocol']} dport {rendered_ports} accept "
                f"comment {_quoted(_rule_marker(identity))}"
            )
            lines.append(
                f"    {ingress} {_quoted(bridge)} {egress} {_quoted(bridge)} "
                f"ip saddr {destination} ip daddr {source} "
                f"ct state established,related accept "
                f"comment {_quoted(_rule_marker(identity + '/reply'))}"
            )
    if family == "inet":
        egress_anchor = anchors.get("egress")
        egress_ports = policy["egress_ports"]
        assert isinstance(egress_ports, list)
        if egress_anchor is not None and egress_ports:
            rendered_ports = (
                str(egress_ports[0])
                if len(egress_ports) == 1
                else "{ " + ", ".join(str(port) for port in egress_ports) + " }"
            )
            denied_ipv4 = "{ " + ", ".join(_EGRESS_DENIED_IPV4) + " }"
            zone_networks = policy["zone_networks"]
            assert isinstance(zone_networks, list)
            egress_network = next(
                str(item["network"])
                for item in zone_networks
                if isinstance(item, Mapping) and item["zone"] == "egress"
            )
            egress_sources = _workload_ipv4(egress_anchor)
            for network_name, source in sorted(egress_sources.items()):
                if network_name != egress_network:
                    continue
                bridge = str(networks[network_name]["bridge"])
                lines.append(
                    f"    oifname {_quoted(bridge)} ip daddr {source} "
                    "ct state established,related accept comment "
                    + _quoted(
                        _rule_marker("platform/egress-broker-reply/" + network_name)
                    )
                )
                lines.append(
                    f"    iifname {_quoted(bridge)} ip saddr {source} "
                    f"ip daddr {denied_ipv4} drop "
                    f"comment {_quoted(_rule_marker('platform/egress-denied-range/' + network_name))}"
                )
                lines.append(
                    f"    iifname {_quoted(bridge)} ip saddr {source} "
                    f"tcp dport {rendered_ports} accept "
                    f"comment {_quoted(_rule_marker('platform/egress-broker/' + network_name))}"
                )
    for bridge in sorted(str(item["bridge"]) for item in networks.values()):
        ingress = "ibrname" if family == "bridge" else "iifname"
        egress = "obrname" if family == "bridge" else "oifname"
        lines.append(
            f"    {ingress} {_quoted(bridge)} drop comment "
            + _quoted(_rule_marker(f"platform/default-ingress/{bridge}"))
        )
        lines.append(
            f"    {egress} {_quoted(bridge)} drop comment "
            + _quoted(_rule_marker(f"platform/default-egress/{bridge}"))
        )
    lines.extend(["  }"])
    if family == "inet":
        for chain, hook, interface in (
            ("host_input", "input", "iifname"),
            ("host_output", "output", "oifname"),
        ):
            lines.extend(
                [
                    f"  chain {chain} {{",
                    f"    type filter hook {hook} priority -300; policy accept;",
                ]
            )
            for bridge in sorted(str(item["bridge"]) for item in networks.values()):
                lines.append(
                    f"    {interface} {_quoted(bridge)} drop comment "
                    + _quoted(_rule_marker(f"platform/{chain}/{bridge}"))
                )
            lines.append("  }")
    lines.append("}")
    return lines


def _seat_protection_table(
    policy: Mapping[str, object], family: str, table_name: str
) -> list[str]:
    """Render only guest-host input protection; never range forwarding."""

    owner = str(policy["owner"])
    digest = _digest(policy)
    networks = _network_index(policy)
    ingress = "ibrname" if family == "bridge" else "iifname"
    lines = [
        f"table {family} {table_name} {{",
        (
            "  comment "
            + _quoted(
                f"aptl-owner={_owner_marker(owner)},authority=seat-protection,digest={digest}"
            )
        ),
        "  chain host_input {",
        "    type filter hook input priority -300; policy accept;",
    ]
    ordered_networks = sorted(networks.values(), key=lambda item: str(item["bridge"]))
    bridges = [str(item["bridge"]) for item in ordered_networks]
    for bridge in bridges:
        lines.append(
            f"    {ingress} {_quoted(bridge)} ct state established,related accept "
            + "comment "
            + _quoted(_rule_marker(f"seat-protection/reply/{bridge}"))
        )
    flows = policy["permitted_flows"]
    assert isinstance(flows, list)
    for flow in flows:
        if not isinstance(flow, Mapping):
            continue
        ports = flow["ports"]
        assert isinstance(ports, list)
        rendered_ports = (
            str(ports[0])
            if len(ports) == 1
            else "{ " + ", ".join(str(port) for port in ports) + " }"
        )
        for network in ordered_networks:
            bridge = str(network["bridge"])
            for address_family, gateway in (
                ("ip", network["ipv4_gateway"]),
                ("ip6", network["ipv6_gateway"]),
            ):
                if gateway is None:
                    continue
                identity = (
                    f"seat-protection/{flow['probe_identity']}/{bridge}/"
                    f"{address_family}"
                )
                lines.append(
                    f"    {ingress} {_quoted(bridge)} {address_family} "
                    f"daddr {gateway} {flow['protocol']} dport {rendered_ports} "
                    "accept comment " + _quoted(_rule_marker(identity))
                )
    for bridge in bridges:
        lines.append(
            f"    {ingress} {_quoted(bridge)} drop comment "
            + _quoted(_rule_marker(f"seat-protection/default/{bridge}"))
        )
    lines.extend(["  }", "}"])
    return lines


def _native_range_table(
    policy: Mapping[str, object], family: str, table_name: str
) -> list[str]:
    """Filter before DNAT so host publications cannot bypass host protection."""
    networks = _network_index(policy)
    bridges = sorted(str(n["bridge"]) for n in networks.values())
    ingress = "ibrname" if family == "bridge" else "iifname"
    egress = "obrname" if family == "bridge" else "oifname"
    lines = [
        f"table {family} {table_name} {{",
        "  comment " + _quoted(_expected_table_comment(policy)),
    ]
    for chain, hook, priority in (
        ("host_input", "input", -150),
        ("forward", "forward", -150),
    ):
        lines += [
            f"  chain {chain} {{",
            f"    type filter hook {hook} priority {priority}; policy accept;",
        ]
        for bridge in bridges:
            prefix = f"    {ingress} {_quoted(bridge)} "
            rules = []
            if chain == "host_input" and family == "bridge":
                rules.extend(
                    [
                        "ether type arp accept",
                        "ether type ip accept",
                        "ether type ip6 accept",
                    ]
                )
            elif chain == "host_input":
                rules.extend(
                    [
                        f"ip6 hoplimit 255 icmpv6 type {kind} accept"
                        for kind in ("nd-neighbor-solicit", "nd-neighbor-advert")
                    ]
                )
                rules.append("ct direction reply ct state established accept")
            else:
                # Replies to operator loopback publications keep their original
                # destination in conntrack; range-initiated published-port
                # connections are denied in prerouting before DNAT.
                rules.append("ct direction reply ct state established accept")
                for target in bridges:
                    rules.append(f"{egress} {_quoted(target)} accept")
                for allowance in policy["allowances"]:
                    address = ipaddress.ip_address(allowance["destination"])
                    selector = "ip" if address.version == 4 else "ip6"
                    rules.append(
                        f"{selector} daddr {address} {allowance['protocol']} dport {allowance['port']} accept"
                    )
            rules.append("drop")
            for order, rule in enumerate(rules):
                lines.append(
                    prefix
                    + rule
                    + " comment "
                    + _quoted(_rule_marker(f"native-range/{chain}/{bridge}/{order}"))
                )
        lines.append("  }")
    if family == "inet":
        lines += [
            "  chain host_destination {",
            "    type filter hook prerouting priority -110; policy accept;",
        ]
        for bridge in bridges:
            for kind in ("nd-neighbor-solicit", "nd-neighbor-advert"):
                lines.append(
                    f"    iifname {_quoted(bridge)} ip6 hoplimit 255 icmpv6 type {kind} accept comment "
                    + _quoted(_rule_marker(f"native-range/nd/{bridge}/{kind}"))
                )
            lines.append(
                f"    iifname {_quoted(bridge)} fib daddr type local ct direction original drop comment "
                + _quoted(_rule_marker(f"native-range/local/{bridge}"))
            )
        lines.append("  }")
    lines.append("}")
    return lines


def render_ruleset(
    raw_policy: object,
    *,
    existing_families: Sequence[str],
) -> str:
    """Render one atomic transaction for exactly one policy authority."""

    policy = validate_policy(raw_policy)
    authority = str(policy["authority"])
    table_name = _table_name(str(policy["owner"]), authority)
    lines: list[str] = []
    for family in ("inet", "bridge"):
        if family in existing_families:
            lines.append(f"delete table {family} {table_name}")
    renderer = {
        "raes": _raes_table,
        "platform": _platform_table,
        "seat-protection": _seat_protection_table,
        "native-range": _native_range_table,
    }[authority]
    lines.extend(renderer(policy, "inet", table_name))
    lines.extend(renderer(policy, "bridge", table_name))
    return "\n".join(lines) + "\n"


def _nft_json(*args: str, input_text: str | None = None) -> dict[str, object]:
    result = subprocess.run(
        ["nft", "-j", *args],
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError("nft operation failed")
    if not result.stdout.strip():
        return {}
    parsed = json.loads(result.stdout)
    if not isinstance(parsed, dict):
        raise RuntimeError("nft observation was invalid")
    return parsed


def _table_objects(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    nftables = payload.get("nftables", [])
    if not isinstance(nftables, list):
        raise RuntimeError("nft observation was invalid")
    return [
        item["table"]
        for item in nftables
        if isinstance(item, dict) and isinstance(item.get("table"), dict)
    ]


def _present_families(table_name: str) -> set[str]:
    """Return the families that nft confirms hold this table; never guess."""

    return {
        str(table.get("family"))
        for table in _table_objects(_nft_json("list", "tables"))
        if table.get("name") == table_name
    }


def _table_comment(family: str, table_name: str) -> str | None:
    for table in _table_objects(_table_payload(family, table_name)):
        comment = table.get("comment")
        if isinstance(comment, str):
            return comment
    return None


def _table_payload(family: str, table_name: str) -> dict[str, object]:
    return _nft_json("list", "table", family, table_name)


def _expected_chains(
    policy: Mapping[str, object],
    family: str,
) -> dict[str, tuple[str | None, int | None, str | None]]:
    if policy["authority"] == "native-range":
        expected = {
            "host_input": ("input", -150, "accept"),
            "forward": ("forward", -150, "accept"),
        }
        if family == "inet":
            expected["host_destination"] = ("prerouting", -110, "accept")
        return expected
    if policy["authority"] == "seat-protection":
        return {"host_input": ("input", -300, "accept")}
    if policy["authority"] == "platform":
        expected = {"forward": ("forward", -300, "accept")}
        if family == "inet":
            expected.update(
                {
                    "host_input": ("input", -300, "accept"),
                    "host_output": ("output", -300, "accept"),
                }
            )
        return expected
    bindings = policy["owner_bindings"]
    assert isinstance(bindings, list)
    expected = {"forward": ("forward", -200, "accept")}
    for binding in bindings:
        if isinstance(binding, Mapping):
            chain = _raes_owner_chain(str(binding["owner_address"]))
            expected[chain] = (None, None, None)
    return expected


# The helpers below give each rendered match in the JSON form that `nft -j list`
# returns. nft drops the protocol matches that a later match implies, sorts the
# elements of an anonymous set, merges adjacent intervals, and lists the
# conntrack state flags as an array.
_ESTABLISHED_OR_RELATED = {
    "match": {
        "op": "in",
        "left": {"ct": {"key": "state"}},
        "right": ["established", "related"],
    }
}


def _json_match(left: object, right: object) -> dict[str, object]:
    return {"match": {"op": "==", "left": left, "right": right}}


def _json_meta(key: str, value: object) -> dict[str, object]:
    return _json_match({"meta": {"key": key}}, value)


def _json_payload(protocol: str, field: str, value: object) -> dict[str, object]:
    return _json_match({"payload": {"protocol": protocol, "field": field}}, value)


def _json_values(values: Sequence[object]) -> object:
    numbers = [value for value in values if isinstance(value, int)]
    if len(numbers) == len(values):
        ordered: list[object] = sorted(set(numbers))
    else:
        addresses = sorted({ipaddress.ip_address(str(value)) for value in values})
        ordered = [str(address) for address in addresses]
    return ordered[0] if len(ordered) == 1 else {"set": ordered}


def _json_prefix(cidr: str) -> object:
    network = ipaddress.ip_network(cidr, strict=False)
    if network.prefixlen == network.max_prefixlen:
        return str(network.network_address)
    return {"prefix": {"addr": str(network.network_address), "len": network.prefixlen}}


def _interface_keys(family: str) -> tuple[str, str]:
    if family == "bridge":
        return "ibrname", "obrname"
    return "iifname", "oifname"


def _json_transport(rule: Mapping[str, object]) -> list[dict[str, object]]:
    protocol = str(rule["protocol"])
    ports = rule["ports"]
    if protocol in {"tcp", "udp"} and isinstance(ports, list) and ports:
        return [_json_payload(protocol, "dport", _json_values(ports))]
    if protocol in {"tcp", "udp", "icmp"}:
        return [_json_meta("l4proto", protocol)]
    return []


ExpectedRules = dict[str, list[tuple[str, list[dict[str, object]]]]]


def _expected_raes_rule(
    policy: Mapping[str, object],
    rule: Mapping[str, object],
    binding: Mapping[str, object],
    family: str,
) -> list[tuple[str, list[dict[str, object]]]]:
    networks = _network_index(policy)
    ingress, egress = _interface_keys(family)
    directions = (
        ("in", "out") if rule["direction"] == "inout" else (str(rule["direction"]),)
    )
    source = rule["from_network"] if isinstance(rule["from_network"], str) else None
    target = rule["to_network"] if isinstance(rule["to_network"], str) else None
    expected = []
    for direction in directions:
        expressions = [
            _json_meta(key, networks[reference]["bridge"])
            for key, reference in ((ingress, source), (egress, target))
            if reference is not None
        ]
        if family == "inet":
            for field, reference in (("saddr", source), ("daddr", target)):
                cidr = networks[reference].get("ipv4_cidr") if reference else None
                if isinstance(cidr, str):
                    expressions.append(_json_payload("ip", field, _json_prefix(cidr)))
        if binding["owner_resource_type"] == "network":
            owner_bridge = networks[str(rule["owner_name"])]["bridge"]
            key = egress if direction == "in" else ingress
            expressions.append(_json_meta(key, owner_bridge))
        else:
            owner_network = target if direction == "in" else source
            addresses = _binding_addresses(binding, owner_network)
            field = "daddr" if direction == "in" else "saddr"
            expressions.append(_json_payload("ip", field, _json_values(addresses)))
        expressions.extend(_json_transport(rule))
        expressions.append(
            {"return": None} if rule["action"] == "allow" else {"drop": None}
        )
        identity = f"{rule['owner_address']}/{rule['name']}/{direction}"
        expected.append((_rule_marker(identity), expressions))
    return expected


def _expected_raes_rules(policy: Mapping[str, object], family: str) -> ExpectedRules:
    networks = _network_index(policy)
    ingress, egress = _interface_keys(family)
    raw_bindings = policy["owner_bindings"]
    raw_rules = policy["rules"]
    assert isinstance(raw_bindings, list)
    assert isinstance(raw_rules, list)
    bindings = [item for item in raw_bindings if isinstance(item, Mapping)]
    rules = [item for item in raw_rules if isinstance(item, Mapping)]
    expected: ExpectedRules = {}
    forward: list[tuple[str, list[dict[str, object]]]] = []
    for binding in bindings:
        owner_address = str(binding["owner_address"])
        chain = _raes_owner_chain(owner_address)
        owner_rules = [rule for rule in rules if rule["owner_address"] == owner_address]
        entries = [
            entry
            for rule in owner_rules
            for entry in _expected_raes_rule(policy, rule, binding, family)
        ]
        entries.append((_rule_marker(f"{owner_address}/default"), [{"return": None}]))
        expected[chain] = entries
        jump = {"jump": {"target": chain}}
        inbound = _rule_marker(f"{owner_address}/dispatch/in")
        outbound = _rule_marker(f"{owner_address}/dispatch/out")
        if binding["owner_resource_type"] == "node":
            addresses = _json_values(_binding_addresses(binding, None))
            forward.append((inbound, [_json_payload("ip", "daddr", addresses), jump]))
            forward.append((outbound, [_json_payload("ip", "saddr", addresses), jump]))
            continue
        for owner_name in sorted({str(rule["owner_name"]) for rule in owner_rules}):
            bridge = networks[owner_name]["bridge"]
            forward.append((inbound, [_json_meta(egress, bridge), jump]))
            forward.append((outbound, [_json_meta(ingress, bridge), jump]))
    expected["forward"] = forward
    return expected


def _expected_platform_crossings(
    policy: Mapping[str, object], family: str
) -> list[tuple[str, list[dict[str, object]]]]:
    anchors = _platform_index(policy)
    networks = _network_index(policy)
    ingress, egress = _interface_keys(family)
    expected = []
    crossings = policy["crossings"]
    assert isinstance(crossings, list)
    for crossing in crossings:
        if not isinstance(crossing, Mapping):
            continue
        sources = _workload_ipv4(anchors[str(crossing["source"])])
        destinations = _workload_ipv4(anchors[str(crossing["destination"])])
        ports = _json_values(crossing["ports"])
        identity = f"platform/{crossing['purpose']}"
        for network_name in sorted(set(sources) & set(destinations)):
            bridge = networks[network_name]["bridge"]
            path = [_json_meta(ingress, bridge), _json_meta(egress, bridge)]
            source, destination = sources[network_name], destinations[network_name]
            expected.append(
                (
                    _rule_marker(identity),
                    path
                    + [
                        _json_payload("ip", "saddr", source),
                        _json_payload("ip", "daddr", destination),
                        _json_payload(str(crossing["protocol"]), "dport", ports),
                        {"accept": None},
                    ],
                )
            )
            expected.append(
                (
                    _rule_marker(identity + "/reply"),
                    path
                    + [
                        _json_payload("ip", "saddr", destination),
                        _json_payload("ip", "daddr", source),
                        _ESTABLISHED_OR_RELATED,
                        {"accept": None},
                    ],
                )
            )
    return expected


def _expected_platform_egress(
    policy: Mapping[str, object],
) -> list[tuple[str, list[dict[str, object]]]]:
    egress_anchor = _platform_index(policy).get("egress")
    egress_ports = policy["egress_ports"]
    if egress_anchor is None or not egress_ports:
        return []
    networks = _network_index(policy)
    zone_networks = policy["zone_networks"]
    assert isinstance(egress_ports, list)
    assert isinstance(zone_networks, list)
    egress_network = next(
        str(item["network"])
        for item in zone_networks
        if isinstance(item, Mapping) and item["zone"] == "egress"
    )
    denied = {
        "set": [
            _json_prefix(str(network))
            for network in ipaddress.collapse_addresses(
                ipaddress.ip_network(cidr) for cidr in _EGRESS_DENIED_IPV4
            )
        ]
    }
    expected = []
    for network_name, source in sorted(_workload_ipv4(egress_anchor).items()):
        if network_name != egress_network:
            continue
        bridge = networks[network_name]["bridge"]
        expected += [
            (
                _rule_marker("platform/egress-broker-reply/" + network_name),
                [
                    _json_meta("oifname", bridge),
                    _json_payload("ip", "daddr", source),
                    _ESTABLISHED_OR_RELATED,
                    {"accept": None},
                ],
            ),
            (
                _rule_marker("platform/egress-denied-range/" + network_name),
                [
                    _json_meta("iifname", bridge),
                    _json_payload("ip", "saddr", source),
                    _json_payload("ip", "daddr", denied),
                    {"drop": None},
                ],
            ),
            (
                _rule_marker("platform/egress-broker/" + network_name),
                [
                    _json_meta("iifname", bridge),
                    _json_payload("ip", "saddr", source),
                    _json_payload("tcp", "dport", _json_values(egress_ports)),
                    {"accept": None},
                ],
            ),
        ]
    return expected


def _expected_platform_rules(
    policy: Mapping[str, object], family: str
) -> ExpectedRules:
    networks = _network_index(policy)
    bridges = sorted(str(item["bridge"]) for item in networks.values())
    ingress, egress = _interface_keys(family)
    forward: list[tuple[str, list[dict[str, object]]]] = []
    if family == "bridge":
        for bridge in bridges:
            path = [_json_meta(ingress, bridge), _json_meta(egress, bridge)]
            neighbor = {"set": ["nd-neighbor-solicit", "nd-neighbor-advert"]}
            forward += [
                (
                    "platform/arp",
                    path + [_json_payload("ether", "type", "arp"), {"accept": None}],
                ),
                (
                    "platform/nd",
                    path
                    + [_json_payload("icmpv6", "type", neighbor), {"accept": None}],
                ),
            ]
    forward += _expected_platform_crossings(policy, family)
    if family == "inet":
        forward += _expected_platform_egress(policy)
    for bridge in bridges:
        forward += [
            (
                _rule_marker(f"platform/default-ingress/{bridge}"),
                [_json_meta(ingress, bridge), {"drop": None}],
            ),
            (
                _rule_marker(f"platform/default-egress/{bridge}"),
                [_json_meta(egress, bridge), {"drop": None}],
            ),
        ]
    expected: ExpectedRules = {"forward": forward}
    if family == "inet":
        for chain, key in (("host_input", "iifname"), ("host_output", "oifname")):
            expected[chain] = [
                (
                    _rule_marker(f"platform/{chain}/{bridge}"),
                    [_json_meta(key, bridge), {"drop": None}],
                )
                for bridge in bridges
            ]
    return expected


def _verify_chain_rules(
    expected: ExpectedRules,
    family: str,
    table_name: str,
    rules: Sequence[Mapping[str, object]],
) -> bool:
    """Compare the ordered expressions of each chain, not only rule identities."""

    observed: dict[str, list[tuple[object, object]]] = {}
    for rule in rules:
        if rule.get("family") != family or rule.get("table") != table_name:
            return False
        entries = observed.setdefault(str(rule.get("chain")), [])
        entries.append((rule.get("comment"), rule.get("expr")))
    return observed == {chain: items for chain, items in expected.items() if items}


def _seat_interface_match(family: str, bridge: str) -> dict[str, object]:
    return _json_meta(_interface_keys(family)[0], bridge)


def _expected_seat_rules(
    policy: Mapping[str, object],
    family: str,
) -> list[tuple[str, list[dict[str, object]]]]:
    networks = _network_index(policy)
    ordered_networks = sorted(networks.values(), key=lambda item: str(item["bridge"]))
    bridges = [str(item["bridge"]) for item in ordered_networks]
    expected: list[tuple[str, list[dict[str, object]]]] = []
    for bridge in bridges:
        interface_match = _seat_interface_match(family, bridge)
        expected.append(
            (
                _rule_marker(f"seat-protection/reply/{bridge}"),
                [interface_match, _ESTABLISHED_OR_RELATED, {"accept": None}],
            )
        )
    flows = policy["permitted_flows"]
    assert isinstance(flows, list)
    for flow in flows:
        if not isinstance(flow, Mapping):
            continue
        ports = flow["ports"]
        assert isinstance(ports, list)
        right = _json_values(ports)
        for network in ordered_networks:
            bridge = str(network["bridge"])
            for address_family, gateway in (
                ("ip", network["ipv4_gateway"]),
                ("ip6", network["ipv6_gateway"]),
            ):
                if gateway is None:
                    continue
                identity = (
                    f"seat-protection/{flow['probe_identity']}/{bridge}/"
                    f"{address_family}"
                )
                expected.append(
                    (
                        _rule_marker(identity),
                        [
                            _seat_interface_match(family, bridge),
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
                                            "protocol": flow["protocol"],
                                            "field": "dport",
                                        }
                                    },
                                    "right": right,
                                }
                            },
                            {"accept": None},
                        ],
                    )
                )
    for bridge in bridges:
        expected.append(
            (
                _rule_marker(f"seat-protection/default/{bridge}"),
                [_seat_interface_match(family, bridge), {"drop": None}],
            )
        )
    return expected


def _verify_seat_rules(
    policy: Mapping[str, object],
    family: str,
    table_name: str,
    rules: Sequence[Mapping[str, object]],
) -> bool:
    expected = _expected_seat_rules(policy, family)
    observed: list[tuple[str, list[object]]] = []
    comments: set[str] = set()
    for rule in rules:
        comment = rule.get("comment")
        expressions = rule.get("expr")
        if (
            not isinstance(comment, str)
            or comment in comments
            or rule.get("family") != family
            or rule.get("table") != table_name
            or rule.get("chain") != "host_input"
            or not isinstance(expressions, list)
        ):
            return False
        comments.add(comment)
        observed.append((comment, expressions))
    return observed == expected


def _verify_native_rules(
    policy: Mapping[str, object],
    family: str,
    table_name: str,
    rules: Sequence[Mapping[str, object]],
) -> bool:
    """Compare ordered native expressions, not just claimed rule identities."""
    expected = []
    ingress = "ibrname" if family == "bridge" else "iifname"
    egress = "obrname" if family == "bridge" else "oifname"
    bridges = sorted(str(n["bridge"]) for n in _network_index(policy).values())

    def match(left, right, op="=="):
        return {"match": {"op": op, "left": left, "right": right}}

    def meta(key, value):
        return match({"meta": {"key": key}}, value)

    for chain in ("host_input", "forward"):
        for bridge in bridges:
            prefix = [meta(ingress, bridge)]
            variants = []
            established = match({"ct": {"key": "state"}}, "established", "in")
            reply = match({"ct": {"key": "direction"}}, "reply")
            if chain == "host_input" and family == "bridge":
                variants += [
                    [
                        match(
                            {"payload": {"protocol": "ether", "field": "type"}}, kind
                        ),
                        {"accept": None},
                    ]
                    for kind in ("arp", "ip", "ip6")
                ]
            else:
                if chain == "host_input":
                    variants += [
                        [
                            match(
                                {"payload": {"protocol": "ip6", "field": "hoplimit"}},
                                255,
                            ),
                            match(
                                {"payload": {"protocol": "icmpv6", "field": "type"}},
                                kind,
                            ),
                            {"accept": None},
                        ]
                        for kind in ("nd-neighbor-solicit", "nd-neighbor-advert")
                    ]
                variants.append([reply, established, {"accept": None}])
            if chain == "forward":
                variants += [
                    [meta(egress, target), {"accept": None}] for target in bridges
                ]
                for allowance in policy["allowances"]:
                    address = ipaddress.ip_address(allowance["destination"])
                    protocol = "ip" if address.version == 4 else "ip6"
                    variants.append(
                        [
                            match(
                                {"payload": {"protocol": protocol, "field": "daddr"}},
                                str(address),
                            ),
                            match(
                                {
                                    "payload": {
                                        "protocol": allowance["protocol"],
                                        "field": "dport",
                                    }
                                },
                                allowance["port"],
                            ),
                            {"accept": None},
                        ]
                    )
            variants.append([{"drop": None}])
            for order, expressions in enumerate(variants):
                expected.append(
                    (
                        chain,
                        _rule_marker(f"native-range/{chain}/{bridge}/{order}"),
                        prefix + expressions,
                    )
                )
    if family == "inet":
        for bridge in bridges:
            for kind in ("nd-neighbor-solicit", "nd-neighbor-advert"):
                expected.append(
                    (
                        "host_destination",
                        _rule_marker(f"native-range/nd/{bridge}/{kind}"),
                        [
                            meta("iifname", bridge),
                            match(
                                {"payload": {"protocol": "ip6", "field": "hoplimit"}},
                                255,
                            ),
                            match(
                                {"payload": {"protocol": "icmpv6", "field": "type"}},
                                kind,
                            ),
                            {"accept": None},
                        ],
                    )
                )
            expected.append(
                (
                    "host_destination",
                    _rule_marker(f"native-range/local/{bridge}"),
                    [
                        meta("iifname", bridge),
                        match({"fib": {"result": "type", "flags": ["daddr"]}}, "local"),
                        match({"ct": {"key": "direction"}}, "original"),
                        {"drop": None},
                    ],
                )
            )
    return [
        (r.get("chain"), r.get("comment"), r.get("expr"))
        for r in rules
        if r.get("family") == family and r.get("table") == table_name
    ] == expected and len(rules) == len(expected)


def _verify_observed_family(
    policy: Mapping[str, object],
    family: str,
) -> bool:
    table_name = _table_name(str(policy["owner"]), str(policy["authority"]))
    payload = _table_payload(family, table_name)
    nftables = payload.get("nftables", [])
    if not isinstance(nftables, list):
        return False
    chains: dict[str, tuple[str | None, int | None, str | None]] = {}
    rules: list[Mapping[str, object]] = []
    for item in nftables:
        if not isinstance(item, dict):
            continue
        chain = item.get("chain")
        if isinstance(chain, dict) and isinstance(chain.get("name"), str):
            chains[str(chain["name"])] = (
                chain.get("hook") if isinstance(chain.get("hook"), str) else None,
                chain.get("prio") if isinstance(chain.get("prio"), int) else None,
                chain.get("policy") if isinstance(chain.get("policy"), str) else None,
            )
        rule = item.get("rule")
        if isinstance(rule, dict) and isinstance(rule.get("comment"), str):
            rules.append(rule)
        elif isinstance(rule, dict):
            return False
    if chains != _expected_chains(policy, family):
        return False
    if policy["authority"] == "native-range":
        return _verify_native_rules(policy, family, table_name, rules)
    if policy["authority"] == "seat-protection":
        return _verify_seat_rules(policy, family, table_name, rules)
    expected_rules = {
        "raes": _expected_raes_rules,
        "platform": _expected_platform_rules,
    }[str(policy["authority"])](policy, family)
    return _verify_chain_rules(expected_rules, family, table_name, rules)


def _owned_families(policy: Mapping[str, object]) -> tuple[str, ...]:
    owner = str(policy["owner"])
    authority = str(policy["authority"])
    table_name = _table_name(owner, authority)
    owned: list[str] = []
    prefix = f"aptl-owner={_owner_marker(owner)},authority={authority},"
    present = _present_families(table_name)
    for family in ("bridge", "inet"):
        if family not in present:
            continue
        comment = _table_comment(family, table_name)
        if comment is None or not comment.startswith(prefix):
            raise RuntimeError("boundary table ownership conflict")
        owned.append(family)
    return tuple(owned)


def _receipt(
    policy: Mapping[str, object],
    families: Sequence[str],
) -> dict[str, object]:
    return {
        "authority": policy["authority"],
        "owner": policy["owner"],
        "enforcement_digest": _digest(policy),
        "families": list(families),
        "default_deny": policy["authority"]
        in {"platform", "seat-protection", "native-range"},
    }


def _expected_table_comment(policy: Mapping[str, object]) -> str:
    return (
        f"aptl-owner={_owner_marker(str(policy['owner']))},"
        f"authority={policy['authority']},digest="
        + (
            _digest(policy).removeprefix("sha256:")
            if policy["authority"] == "native-range"
            else _digest(policy)
        )
    )


def _apply(policy: dict[str, object]) -> dict[str, object]:
    existing = _owned_families(policy)
    rendered = render_ruleset(policy, existing_families=existing)
    _nft_json("-f", "-", input_text=rendered)
    observed = _owned_families(policy)
    if observed != ("bridge", "inet"):
        raise RuntimeError("boundary tables were not observed")
    if any(
        _table_comment(
            family, _table_name(str(policy["owner"]), str(policy["authority"]))
        )
        != _expected_table_comment(policy)
        for family in observed
    ):
        raise RuntimeError("boundary table readback did not match")
    if not all(_verify_observed_family(policy, family) for family in observed):
        raise RuntimeError("boundary rule readback did not match")
    return _receipt(policy, observed)


def _cleanup(policy: dict[str, object]) -> dict[str, object]:
    existing = _owned_families(policy)
    table_name = _table_name(str(policy["owner"]), str(policy["authority"]))
    if existing:
        rendered = "\n".join(
            f"delete table {family} {table_name}" for family in existing
        )
        _nft_json("-f", "-", input_text=rendered + "\n")
    if _owned_families(policy):
        raise RuntimeError("boundary cleanup was not observed")
    return _receipt(policy, ())


def _observe(policy: dict[str, object]) -> dict[str, object]:
    families = _owned_families(policy)
    if families != ("bridge", "inet"):
        raise RuntimeError("boundary tables are incomplete")
    table_name = _table_name(str(policy["owner"]), str(policy["authority"]))
    for family in families:
        if _table_comment(family, table_name) != _expected_table_comment(policy):
            raise RuntimeError("boundary policy digest mismatch")
        if not _verify_observed_family(policy, family):
            raise RuntimeError("boundary rule readback did not match")
    return _receipt(policy, families)


def _check(policy: dict[str, object]) -> dict[str, object]:
    """Check kernel support and permissions without installing any rule."""
    _nft_json(
        "--check",
        "-f",
        "-",
        input_text=render_ruleset(policy, existing_families=_owned_families(policy)),
    )
    return {"supported": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("apply", "observe", "cleanup", "check"))
    parser.add_argument("--stdin", action="store_true", required=True)
    args = parser.parse_args()
    try:
        policy = validate_policy(json.load(sys.stdin))
        action = {
            "apply": _apply,
            "observe": _observe,
            "cleanup": _cleanup,
            "check": _check,
        }[args.action]
        print(json.dumps(action(policy), sort_keys=True, separators=(",", ":")))
        return 0
    except (
        ValueError,
        RuntimeError,
        KeyError,
        TypeError,
        OSError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
    ):
        print("boundary helper failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
