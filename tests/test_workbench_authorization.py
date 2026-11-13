"""Browser profiles are an authorization boundary, not a UI filter."""

from types import SimpleNamespace

from fastapi.testclient import TestClient


def test_browser_enforces_role_and_caller_on_every_action():
    from aptl.workbench.app import BrowserPrincipal, create_participant_workbench_app

    class Runtime:
        current_launch = None

        def switch(self, profile):
            self.current_launch = SimpleNamespace(
                profile=SimpleNamespace(value=profile), run_id="a" * 32
            )
            return self.current_launch

        def respond(self, message):
            return "allowed"

        def close(self):
            self.current_launch = None

    runtime = Runtime()
    alice = BrowserPrincipal(caller_id="alice", profiles=("red",))
    bob = BrowserPrincipal(caller_id="bob", profiles=("blue",))
    caller = [alice]
    client = TestClient(create_participant_workbench_app(runtime, lambda _: caller[0]))
    assert client.post("/workbench/profiles/blue").status_code == 403
    assert client.post("/workbench/profiles/red").status_code == 200
    caller[0] = bob
    assert (
        client.post("/workbench/messages", json={"message": "inspect"}).status_code
        == 403
    )
    assert client.delete("/workbench/profile").status_code == 403
    assert client.get("/workbench").status_code == 403
    caller[0] = True  # Boolean authentication cannot silently grant every role.
    assert client.post("/workbench/profiles/blue").status_code == 401


def test_local_workbench_renderer_uses_guest_dispatch_not_direct_node(tmp_path):
    import json
    from pathlib import Path

    from aptl.workbench.bootstrap import render_guest_workbench_config
    from aptl.workbench.guest_binding import GuestDispatchBinding
    from aptl.workbench.profiles import ProfileId
    from tests.test_mcp_access import access_record, grant

    binding = GuestDispatchBinding(
        schema_version="aptl.mcp-dispatch/v1",
        access=access_record(),
        grants=(grant(),),
        project_dir=tmp_path,
        node_executable=Path("/usr/bin/node"),
        management_home=tmp_path,
        run_id="run_20260917T120000Z",
        delivery="rootful-integration",
    )
    binding_path = tmp_path / "binding.json"
    binding_path.write_text(binding.model_dump_json())
    binding_path.chmod(0o600)
    path = render_guest_workbench_config(
        binding_path=binding_path,
        grant_id="grant-1",
        profile=ProfileId.RED,
        run_id=binding.run_id,
        executable=Path("/usr/bin/aptl"),
        output=tmp_path / "configs",
    )
    document = json.loads(path.read_text())
    server = document["mcpServers"]["aptl-red"]
    assert server["command"] == "/usr/bin/aptl"
    assert server["args"][:2] == ["mcp-access", "dispatch"]
    assert server["env"] == {
        "SSH_ORIGINAL_COMMAND": "aptl-mcp-v1 instance-1 1 aptl-red"
    }
    assert "ANTHROPIC" not in path.read_text()
    import pytest

    with pytest.raises(ValueError):
        render_guest_workbench_config(
            binding_path=binding_path,
            grant_id="grant-1",
            profile=ProfileId.BLUE,
            run_id=binding.run_id,
            executable=Path("/usr/bin/aptl"),
            output=tmp_path / "other",
        )
