"""Native range firewall validation and semantic readback regressions."""

import copy
import importlib.util
import json
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import MagicMock

import pytest

from aptl.core.config import DeploymentConfig
from aptl.core.deployment.boundary import (
    BoundaryNetwork,
    NativeRangeBoundarySpec,
    NativeRangeAllowance,
)
from aptl.core.deployment.docker_compose import DockerComposeBackend


@pytest.fixture
def helper():
    path = Path(__file__).parents[1] / "containers/network-boundary-helper/helper.py"
    spec = importlib.util.spec_from_file_location("native_helper", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def policy():
    return NativeRangeBoundarySpec(
        "range-968",
        (
            BoundaryNetwork("security-net", "br-security", ipv4_cidr="10.240.0.0/24"),
            BoundaryNetwork(
                "internal-net",
                "br-internal",
                ipv4_cidr="10.241.0.0/24",
                ipv6_cidr="fd00:968::/64",
            ),
        ),
        (NativeRangeAllowance("192.0.2.8", "tcp", 443),),
    )


@pytest.mark.parametrize(
    "allowance",
    [
        {"destination": "example.com", "protocol": "tcp", "port": 443},
        {"destination": "0.0.0.0/0", "protocol": "tcp", "port": 443},
        {"destination": "127.0.0.1", "protocol": "tcp", "port": 443},
        {"destination": "192.0.2.8", "protocol": "any", "port": 443},
        {"destination": "192.0.2.8", "protocol": "udp", "port": True},
    ],
)
def test_allowance_is_exact(allowance):
    with pytest.raises(ValueError):
        DeploymentConfig(range_egress_allowances=[allowance])


def test_floor_covers_every_bridge_and_preserves_topology(helper, policy):
    raw = policy.details()
    before = copy.deepcopy(raw)
    text = helper.render_ruleset(raw, existing_families=[])
    assert raw == before
    assert "ip daddr 192.0.2.8 tcp dport 443 accept" in text
    assert "fib daddr type local ct direction original drop" in text
    for bridge in ("br-security", "br-internal"):
        assert f'iifname "{bridge}" drop' in text
        assert f'ibrname "{bridge}" drop' in text
    assert "ct direction reply ct state established accept" in text
    assert "ip6 daddr" not in text  # no implicit IPv6 external grant


def test_failed_apply_never_records_success(tmp_path, policy):
    backend = DockerComposeBackend(tmp_path)
    backend._run = MagicMock(return_value=CompletedProcess([], 0, "", ""))
    backend._run_with_input = MagicMock(return_value=CompletedProcess([], 1, "", ""))
    assert not backend.realize_boundary(policy).success
    assert "native-range" not in backend._boundary_receipts


def test_partial_readback_never_records_success(tmp_path, policy):
    backend = DockerComposeBackend(tmp_path)
    backend._run = MagicMock(return_value=CompletedProcess([], 0, "", ""))
    backend._run_with_input = MagicMock(
        side_effect=[
            CompletedProcess([], 0, "", ""),
            CompletedProcess([], 0, json.dumps({"authority": "native-range"}), ""),
        ]
    )
    assert not backend.realize_boundary(policy).success
    assert "native-range" not in backend._boundary_receipts


def test_owned_table_replacement(helper, policy):
    text = helper.render_ruleset(policy.details(), existing_families=["inet", "bridge"])
    table = helper._table_name(policy.owner, "native-range")
    assert text.startswith(f"delete table inet {table}\ndelete table bridge {table}\n")
    assert "flush ruleset" not in text
    assert helper._table_name("another-range", "native-range") not in text


def test_native_preflight_refuses_socket_authority_before_helper(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from aptl.core import execution_boundary

    backend = DockerComposeBackend(tmp_path)
    backend._run = MagicMock()
    monkeypatch.setattr(
        execution_boundary,
        "revalidate_execution_boundary",
        lambda _: SimpleNamespace(host_containment="native-docker"),
    )
    realization = SimpleNamespace(docker_authority_admissions=(object(),), nodes=())
    result = backend._native_range_preflight(realization)
    assert not result.success
    assert "socket authority" in result.error
    backend._run.assert_not_called()


def test_native_compose_creates_stopped_resources_before_enforcement(
    tmp_path, monkeypatch, policy
):
    from types import SimpleNamespace
    from aptl.core import execution_boundary
    from aptl.core.lab_types import LabResult

    backend = DockerComposeBackend(tmp_path)
    monkeypatch.setattr(
        execution_boundary,
        "revalidate_execution_boundary",
        lambda _: SimpleNamespace(host_containment="native-docker"),
    )
    events = []

    def command(argv):
        events.append("config" if "config" in argv else "create")
        return CompletedProcess(
            argv, 0, json.dumps({"services": {"node": {"networks": {"range": {}}}}}), ""
        )

    backend._run = command
    backend._build_command = lambda action, profiles, **kwargs: [
        "docker",
        "compose",
        action,
    ]
    backend._capture_started_resources = lambda *args, **kwargs: LabResult(success=True)
    backend.host_list_lab_networks = lambda _: ["range"]
    backend._resolve_owned_network_id = lambda _: "native-id"
    backend._project_boundary_network_observations = lambda: policy.networks

    def enforce(spec):
        events.append("enforce")
        assert spec.networks == policy.networks
        return LabResult(success=True)

    backend.realize_boundary = enforce
    scope = SimpleNamespace(compose_files=())
    assert (
        backend._native_compose_floor(scope, [], ["docker", "compose", "up", "-d"])
        is None
    )
    assert events == ["config", "create", "enforce"]


def test_native_boundary_disclosure_requires_bound_verified_receipt(tmp_path, policy):
    from aptl.core.execution_boundary import (
        ExecutionBoundaryObservation,
        disclosed_execution_boundary,
    )

    backend = DockerComposeBackend(tmp_path)
    backend._execution_boundary_disclosure = ExecutionBoundaryObservation(
        transport="local-unix",
        override_source="none",
        daemon_runtime="native-linux",
        host_containment="native-docker",
        observation_status="observed",
        host_os="linux",
    )
    assert disclosed_execution_boundary(backend).range_egress_policy == "unverified"
    backend._record_boundary_receipt(policy)
    reported = disclosed_execution_boundary(backend)
    assert reported.range_egress_policy == "default-deny"
    assert reported.range_host_access_policy == "deny"
    assert reported.range_policy_digest == policy.digest()


@pytest.mark.parametrize("mode", ["host", "container:foreign", "service:missing"])
def test_native_namespace_bypass_is_refused(mode):
    from aptl.core.deployment._native_range_model import validate_native_services

    def refuse(_):
        raise ValueError("foreign container")

    with pytest.raises((ValueError, KeyError)):
        validate_native_services({"node": {"network_mode": mode}}, refuse)


def test_native_capture_namespace_stays_in_range():
    from aptl.core.deployment._native_range_model import validate_native_services

    validate_native_services(
        {"node": {}, "capture": {"network_mode": "service:node"}}, lambda _: "owned"
    )


@pytest.mark.parametrize(
    "service",
    [
        {"privileged": True},
        {"devices": ["/dev/kvm"]},
        {"cap_add": ["SYS_ADMIN"]},
        {"volumes": [{"source": "/run/docker.sock"}]},
        {"volumes": [{"source": "/run/user/1000/podman/podman.sock"}]},
        {"volumes": [{"source": "/"}]},
    ],
)
def test_native_host_authority_is_refused(service):
    from aptl.core.deployment._native_range_model import validate_native_services

    with pytest.raises(ValueError):
        validate_native_services({"node": service}, lambda _: "owned")


@pytest.mark.parametrize("family", ["bridge", "inet"])
@pytest.mark.parametrize(
    "mutation", [None, "verdict", "interface", "port", "missing", "reordered"]
)
def test_kernel_readback_fixture_detects_semantic_mutations(
    helper, monkeypatch, family, mutation
):
    # Captured from nftables 1.1.6 in an isolated Docker network namespace.
    # Handles are omitted; expressions and ordering are the actual kernel output.
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/native-range/kernel-readback.json"
        ).read_text()
    )
    policy = fixture["policy"]
    items = [
        item
        for item in fixture["readback"]["nftables"]
        if next(iter(item.values())).get("family") == family
    ]
    rules = [item["rule"] for item in items if "rule" in item]
    if mutation == "verdict":
        rule = next(r for r in rules if r["expr"][-1] == {"drop": None})
        rule["expr"][-1] = {"accept": None}
    elif mutation == "interface":
        rules[0]["expr"][0]["match"]["right"] = "br-foreign"
    elif mutation == "port":
        expression = next(
            e
            for r in rules
            for e in r["expr"]
            if e.get("match", {}).get("left", {}).get("payload", {}).get("field")
            == "dport"
        )
        expression["match"]["right"] = 444
    elif mutation == "missing":
        items.remove(next(item for item in items if "rule" in item))
    elif mutation == "reordered":
        indices = [i for i, item in enumerate(items) if "rule" in item]
        items[indices[0]], items[indices[1]] = items[indices[1]], items[indices[0]]
    monkeypatch.setattr(helper, "_table_payload", lambda *args: {"nftables": items})
    assert helper._verify_observed_family(policy, family) is (mutation is None)


@pytest.mark.parametrize("supported", [True, False])
def test_native_kernel_check_is_a_predeployment_gate(tmp_path, monkeypatch, supported):
    from types import SimpleNamespace
    from aptl.core import execution_boundary
    from aptl.core.deployment import _compose_boundary

    backend = DockerComposeBackend(tmp_path)
    monkeypatch.setattr(
        execution_boundary,
        "revalidate_execution_boundary",
        lambda _: SimpleNamespace(host_containment="native-docker"),
    )
    monkeypatch.setattr(_compose_boundary, "_ensure_helper", lambda *args: None)
    calls = []

    def checked(*args):
        calls.append(args)
        return CompletedProcess([], 0 if supported else 1, "", "")

    monkeypatch.setattr(_compose_boundary, "_run_helper", checked)
    result = backend._native_range_preflight()
    assert (result is None) is supported
    assert calls[0][1] == "check"
    if not supported:
        assert "before deployment" in result.error


@pytest.mark.parametrize("success", [True, False])
def test_native_boundary_binds_all_observed_networks_before_start(
    tmp_path, monkeypatch, policy, success
):
    from types import SimpleNamespace
    from aptl.core import execution_boundary
    from aptl.core.lab_types import LabResult

    backend = DockerComposeBackend(tmp_path)
    monkeypatch.setattr(
        execution_boundary,
        "revalidate_execution_boundary",
        lambda _: SimpleNamespace(host_containment="native-docker"),
    )
    backend._project_boundary_network_observations = lambda: policy.networks
    backend._range_egress_allowances = policy.allowances
    backend.realize_boundary = MagicMock(
        return_value=LabResult(
            success=success, error=None if success else "mutation failed"
        )
    )
    result = backend._realize_native_range_boundary(object())
    assert (result is None) is success
    applied = backend.realize_boundary.call_args.args[0]
    assert applied.networks == policy.networks
    assert applied.allowances == policy.allowances


def test_native_boundary_summary_reports_applied_policy(capsys):
    from aptl.cli.lab_render import emit_execution_boundary_summary
    from aptl.core.execution_boundary import ExecutionBoundaryObservation

    boundary = ExecutionBoundaryObservation(
        transport="local-unix",
        override_source="none",
        daemon_runtime="native-linux",
        host_containment="native-docker",
        observation_status="observed",
        host_os="linux",
        range_egress_policy="default-deny",
        range_host_access_policy="deny",
    )
    emit_execution_boundary_summary(boundary)
    output = capsys.readouterr().out
    assert "range egress: default-deny" in output
    assert "range-to-host access: deny" in output
