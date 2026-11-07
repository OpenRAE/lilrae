"""Scenario-bound MCP selection, fresh discovery, and operator policy (#1244)."""

import json
from types import SimpleNamespace

import pytest

from aptl.core.lab import _sync_mcp_config_keys
from aptl.core.mcp_policy import (
    WorkbenchConfigurationError,
    configured_server_ids,
    profile_for,
)
from aptl.workbench.access import authorize_server
from tests.test_mcp_access import access_record, grant


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
    record, caller = access_record(mcp_server_ids=()), grant()
    with pytest.raises(ValueError, match="not authorized"):
        authorize_server(record, caller, "aptl-red")


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
