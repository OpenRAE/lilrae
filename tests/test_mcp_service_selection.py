"""Scenario-bound MCP selection, fresh discovery, and operator policy (#1244)."""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from aptl.core.config import AptlConfig
from aptl.core.lab import _runtime_mcp_host_ports, _sync_mcp_config_keys
from aptl.core.mcp_policy import (
    McpPolicy,
    SERVER_IDS,
    WorkbenchConfigurationError,
    configured_server_ids,
    profile_for,
    select_scenario_servers,
)
from aptl.core.scenario_bundle import env_pack_bundle
from aptl.workbench.access import authorize_server
from tests.test_mcp_access import access_record, grant


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
    with pytest.raises(WorkbenchConfigurationError, match="no declared service"):
        select_scenario_servers(
            techvault, McpPolicy(required_servers=("aptl-threatintel",))
        )
    with pytest.raises(ValueError, match="invalid operator MCP policy"):
        AptlConfig(mcp={"allowed_servers": ["unapproved-pack-server"]})
    with pytest.raises(ValueError, match="invalid operator MCP policy"):
        McpPolicy(allowed_servers=(), required_servers=("aptl-red",))


def test_matching_node_without_declared_service_cannot_admit_server(techvault):
    techvault.nodes["misp"].services = []
    assert "aptl-threatintel" not in select_scenario_servers(techvault, McpPolicy())


class _Backend:
    def __init__(self, misp_port):
        self.misp_port = misp_port

    def container_list(self, **kwargs):
        return [{"Service": "misp", "Name": "owned-misp"}]

    def container_inspect(self, name):
        if name != "owned-misp":
            return {}
        return {
            "NetworkSettings": {
                "Ports": {"443/tcp": [{"HostPort": str(self.misp_port)}]}
            }
        }


def test_present_absent_present_rebuilds_discovery_endpoints_and_tools(
    tmp_path, techvault
):
    template = json.loads((Path(__file__).parents[1] / ".mcp.json.example").read_text())
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
            with pytest.raises(ValueError, match="not authorized"):
                authorize_server(record, grant(profile="blue"), "aptl-threatintel")
        assert config != previous_config
        previous_config = deepcopy(config)


def test_selected_endpoint_readiness_failure_keeps_previous_config_private(tmp_path):
    template = {
        "mcpServers": {"aptl-threatintel": {"env": {"APTL_HP_MISP_443": "1443"}}}
    }
    path = tmp_path / ".mcp.json"
    path.write_text(json.dumps(template))
    (tmp_path / ".env").write_text("MISP_API_KEY=fixture-key\n")
    before = path.read_bytes()
    with pytest.raises(WorkbenchConfigurationError, match="endpoint is unavailable"):
        _sync_mcp_config_keys(
            tmp_path, [], server_ids=("aptl-threatintel",), run_id="c" * 32
        )
    assert path.read_bytes() == before
    with pytest.raises(WorkbenchConfigurationError, match="another run"):
        configured_server_ids(tmp_path, "c" * 32)


def test_guest_record_without_selection_grants_no_legacy_authority():
    with pytest.raises(ValueError, match="not authorized"):
        authorize_server(access_record(mcp_server_ids=()), grant(), "aptl-red")


def test_fresh_workbench_sessions_do_not_retain_selected_out_tools(tmp_path):
    from aptl.core.runstore import LocalRunStore
    from aptl.core.session import ScenarioSession
    from aptl.workbench.runtime import WorkbenchRuntime
    from tests.test_participant_workbench import (
        _FakeAdapter,
        _FakeCredentials,
        _payload_with_all_artifacts,
        _runtime_paths,
    )

    class SelectedAdapter(_FakeAdapter):
        def list_tools(self, handle):
            return {
                server.server_id: server.tool_names
                for server in profile_for(
                    handle.profile, server_ids=handle.server_ids
                ).servers
            }

    session = ScenarioSession(tmp_path / "state")
    payload = _payload_with_all_artifacts(tmp_path / "payload")
    adapter = SelectedAdapter()
    runtime = WorkbenchRuntime(
        session,
        adapter,
        LocalRunStore(tmp_path / "runs"),
        paths=_runtime_paths(payload, tmp_path / "generated"),
        credential_broker=_FakeCredentials(),
        model="fixture",
    )
    launches = []
    for port in (1443, None, 3443):
        active = session.start("service-selection")
        servers = (
            {}
            if port is None
            else {
                "aptl-threatintel": {
                    "env": {
                        "APTL_MCP_ADMITTED_RUN_ID": active.trace_id,
                        "APTL_HP_MISP_443": str(port),
                    }
                }
            }
        )
        (payload / ".mcp.json").write_text(json.dumps({"mcpServers": servers}))
        launch = runtime.start("blue")
        launches.append(launch)
        config = json.loads(launch.client_config_path.read_text())["mcpServers"]
        assert set(config) == set(servers)
        if port is not None:
            assert config["aptl-threatintel"]["env"]["APTL_HP_MISP_443"] == str(port)
        runtime.close()
        assert not launch.client_config_path.exists()
        session.finish()
        session.clear()
    assert len({launch.run_id for launch in launches}) == 3
    assert len(adapter.closed_profiles) == 3


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
    with pytest.raises(WorkbenchConfigurationError, match="no declared service"):
        raes.admit_raes_scenario(
            tmp_path,
            AptlConfig(mcp={"required_servers": ["aptl-threatintel"]}),
            object(),
            source=ScenarioAdmissionSource(bundle=bundle),
        )


def test_empty_selection_clears_old_config_even_without_credentials(tmp_path):
    path = tmp_path / ".mcp.json"
    path.write_text(json.dumps({"mcpServers": {"aptl-threatintel": {"env": {}}}}))
    _sync_mcp_config_keys(tmp_path, [], server_ids=(), run_id="d" * 32)
    assert json.loads(path.read_text())["mcpServers"] == {}


def test_guest_admission_projection_retains_exact_reduced_inventory(tmp_path):
    from aptl.core.lab import _persist_mcp_run_admission
    from aptl.core.mcp_policy import McpRunAdmission

    record = access_record()
    ctx = SimpleNamespace(
        project_dir=tmp_path,
        run_id="a" * 32,
        admitted_start=SimpleNamespace(
            bundle=SimpleNamespace(pack_identity=record.scenario_pack),
            mcp_server_ids=("aptl-threatintel",),
            realization=SimpleNamespace(
                nodes=(
                    SimpleNamespace(
                        name="misp",
                        container_name="aptl-misp",
                        backend_services=("misp",),
                    ),
                )
            ),
        ),
    )
    _persist_mcp_run_admission(ctx)
    path = tmp_path / ".aptl/mcp-admission.json"
    admitted = McpRunAdmission.model_validate_json(path.read_bytes())
    assert admitted.server_ids == ("aptl-threatintel",)
    assert admitted.run_id == ctx.run_id
    assert len(admitted.container_aliases) == 1
    assert "misp" in admitted.container_aliases[0]
    assert path.stat().st_mode & 0o777 == 0o600
