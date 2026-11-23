"""MCP selection follows the released TechVault declared services (#1700)."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from aptl.core.config import AptlConfig
from aptl.core.lab import _runtime_mcp_host_ports, _sync_mcp_config_keys
from aptl.core.mcp_policy import (
    SERVER_IDS,
    McpPolicy,
    WorkbenchConfigurationError,
    configured_server_ids,
    profile_for,
    select_scenario_servers,
)
from aptl.core.scenario_bundle import env_pack_bundle
from aptl.workbench.access import authorize_server
from tests.test_mcp_access import access_record, grant
from tests.test_mcp_service_selection import _Backend


@pytest.fixture
def techvault(tmp_path):
    from raes import parse_sdl_file

    bundle = env_pack_bundle(tmp_path / "pack", "techvault")
    return parse_sdl_file(bundle.sdl_path)


def test_full_techvault_and_partial_soc_follow_declared_services(techvault):
    assert set(select_scenario_servers(techvault, McpPolicy())) == set(SERVER_IDS)
    small = techvault.model_copy(deep=True)
    small.nodes = {
        name: small.nodes[name] for name in ("wazuh-manager", "wazuh-indexer")
    }
    selected = select_scenario_servers(small, McpPolicy())
    assert set(selected) == {"aptl-indexer", "aptl-wazuh"}
    assert profile_for("blue", server_ids=selected).server_ids == (
        "aptl-indexer",
        "aptl-wazuh",
    )
    small.nodes.pop("wazuh-manager")
    assert select_scenario_servers(small, McpPolicy()) == ()


def test_operator_ceiling_and_required_server_fail_before_deployment(techvault):
    policy = McpPolicy(allowed_servers=("aptl-indexer",))
    assert select_scenario_servers(techvault, policy) == ("aptl-indexer",)
    techvault.nodes.pop("misp")
    required = McpPolicy(required_servers=("aptl-threatintel",))
    with pytest.raises(WorkbenchConfigurationError, match="no declared service"):
        select_scenario_servers(techvault, required)
    with pytest.raises(ValueError, match="invalid operator MCP policy"):
        AptlConfig(mcp={"allowed_servers": ["unapproved-pack-server"]})
    with pytest.raises(ValueError, match="invalid operator MCP policy"):
        McpPolicy(allowed_servers=(), required_servers=("aptl-red",))


def test_matching_node_without_declared_service_cannot_admit_server(techvault):
    techvault.nodes["misp"].services = []
    assert "aptl-threatintel" not in select_scenario_servers(techvault, McpPolicy())


def test_present_absent_present_rebuilds_discovery_endpoints_and_tools(
    tmp_path, techvault
):
    template = json.loads((Path(__file__).parents[2] / ".mcp.json.example").read_text())
    (tmp_path / ".mcp.json.example").write_text(json.dumps(template))
    (tmp_path / ".env").write_text("MISP_API_KEY=fixture-key\n")
    policy = McpPolicy(allowed_servers=("aptl-threatintel",))
    removed = techvault.model_copy(deep=True)
    removed.nodes.pop("misp")
    previous_config = None
    for scenario, run_id, port in (
        (techvault, "a" * 32, 1443),
        (removed, "b" * 32, 2443),
        (techvault, "c" * 32, 3443),
    ):
        selected = select_scenario_servers(scenario, policy)
        ports = _runtime_mcp_host_ports(tmp_path, _Backend(port), server_ids=selected)
        _sync_mcp_config_keys(tmp_path, ports, server_ids=selected, run_id=run_id)
        discovered = configured_server_ids(tmp_path, run_id)
        assert discovered == selected
        profile = profile_for("blue", server_ids=discovered)
        assert bool(profile.servers) == (scenario is techvault)
        config = json.loads((tmp_path / ".mcp.json").read_text())
        assert set(config["mcpServers"]) == set(selected)
        record = access_record(mcp_server_ids=selected)
        if selected:
            assert config["mcpServers"]["aptl-threatintel"]["env"][
                "APTL_HP_MISP_443"
            ] == str(port)
            assert authorize_server(
                record, grant(profile="blue"), "aptl-threatintel"
            ).tool_names
        else:
            assert profile.credential_aliases == ()
            caller = grant(profile="blue")
            with pytest.raises(ValueError, match="not authorized"):
                authorize_server(record, caller, "aptl-threatintel")
        assert config != previous_config
        previous_config = deepcopy(config)


def test_required_absent_service_rejects_before_runtime_admission(
    tmp_path, techvault, monkeypatch
):
    from aptl.backends import raes
    from aptl.backends.raes_start_model import ScenarioAdmissionSource
    from aptl.core.scenario_bundle import project_tree_bundle

    techvault.nodes.pop("misp")
    bundle = project_tree_bundle(tmp_path, tmp_path / "unused.sdl.yaml")
    monkeypatch.setattr(raes, "resolve_admission_adapters", lambda *args: (None, None))
    monkeypatch.setattr(
        raes,
        "prepare_admission_scenario",
        lambda *args, **kwargs: (techvault, None, None),
    )
    monkeypatch.setattr(
        raes,
        "prepare_runtime_orchestration_for_scenario",
        lambda *args: pytest.fail("runtime must not be admitted"),
    )
    config = AptlConfig(mcp={"required_servers": ["aptl-threatintel"]})
    backend = object()
    source = ScenarioAdmissionSource(bundle=bundle)
    with pytest.raises(WorkbenchConfigurationError, match="no declared service"):
        raes.admit_raes_scenario(tmp_path, config, backend, source=source)
