"""Browser ingress rechecks live capture with the TechVault guide (#1700)."""

from fastapi.testclient import TestClient


def test_canonical_browser_ingress_rechecks_live_capture_and_grant(
    tmp_path, monkeypatch
):
    from pathlib import Path

    from aptl.core.scenario_bundle import env_pack_bundle
    from aptl.workbench import guest_binding
    from aptl.workbench.app import BrowserPrincipal
    from aptl.workbench.bootstrap import (
        ApplianceWorkbenchSettings,
        create_local_workbench_app,
    )
    from aptl.workbench.guest_binding import GuestDispatchBinding
    from tests.test_mcp_access import access_record, grant

    pack = env_pack_bundle(tmp_path / "pack", "techvault")
    record = access_record(scenario_pack=pack.pack_identity)
    caller = grant()
    binding = GuestDispatchBinding(
        schema_version="aptl.mcp-dispatch/v1",
        access=record,
        grants=(caller,),
        project_dir=tmp_path,
        node_executable=Path("/usr/bin/node"),
        management_home=tmp_path,
        run_id="a" * 32,
        delivery="rootful-integration",
    )
    path = tmp_path / "binding.json"
    path.write_text(binding.model_dump_json())
    path.chmod(0o600)
    observation = dict(
        boot_id=record.guest_boot_id,
        daemon_id=record.guest_daemon_id,
        project=record.guest_project,
        containers=record.container_ids,
        run_id=binding.run_id,
        capture={"ready": True, "run_id": binding.run_id},
    )
    monkeypatch.setattr(guest_binding, "observe_guest", lambda _: observation)
    settings = ApplianceWorkbenchSettings(
        payload_root=tmp_path,
        state_dir=tmp_path / "state",
        claude_executable=Path("/usr/bin/false"),
        model="test",
    )
    app = create_local_workbench_app(
        settings,
        binding_path=path,
        grant_id=caller.grant_id,
        aptl_executable=Path("/usr/bin/false"),
        secret_source={},
        authorizer=lambda request: (
            BrowserPrincipal(caller.grant_id, ("red",))
            if request.headers.get("X-Seat") == "admitted"
            else None
        ),
    )
    client = TestClient(app)
    assert client.get("/").status_code == 401
    headers = {"X-Seat": "admitted"}
    assert client.get("/", headers=headers).status_code == 200
    assert client.get("/guide/", headers=headers).status_code == 200
    assert client.get("/api/lab/status", headers=headers).status_code == 404
    assert client.post("/workbench/profiles/blue", headers=headers).status_code == 403
    observation["capture"]["ready"] = False
    assert client.get("/", headers=headers).status_code == 401
    observation["capture"]["ready"] = True
    path.write_text(
        binding.model_copy(
            update={"grants": (caller.model_copy(update={"revoked": True}),)}
        ).model_dump_json()
    )
    assert client.get("/", headers=headers).status_code == 401
