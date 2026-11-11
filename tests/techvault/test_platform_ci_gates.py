"""The capture lifecycle lane runs the TechVault transcript test (#1700)."""

from __future__ import annotations

from tests.test_platform_ci_gates import _run_step, _shell, _stub


def test_capture_lifecycle_lane_requires_docker_and_propagates_test_failure(tmp_path):
    script = "set -e\n" + _run_step(
        "mcp-tests", "Extracted MCP shutdown through the real capture sidecar"
    )
    for name in ("node", "ssh", "ssh-keygen"):
        _stub(tmp_path, name, "exit 0")
    probe = tmp_path / "pytest-invocation"
    for daemon_status, test_status in ((19, 0), (0, 23), (0, 0)):
        probe.unlink(missing_ok=True)
        _stub(tmp_path, "docker", f"exit {daemon_status}")
        _stub(
            tmp_path,
            "python",
            f'printf "%s\\n" "$*" > "$LILRAE_TEST_CAPTURE_PROBE"\nexit {test_status}',
        )
        result = _shell(script, tmp_path, LILRAE_TEST_CAPTURE_PROBE=str(probe))
        assert result.returncode == (daemon_status or test_status)
        if daemon_status:
            assert not probe.exists()
        else:
            assert "tests/techvault/test_mcp_capture_lifecycle.py" in probe.read_text()
            assert "-m integration" in probe.read_text()
