"""Installed-wheel qualification across OpenCode, MCP and runtime admission."""

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tests.opencode_fixture import install_wheel
from tests.test_opencode_transport import opencode_binary

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "mode",
    [
        "authorized",
        "forbidden-arguments",
        "builtin-shell",
        "timeout",
        "cancel",
        "malformed",
        "teardown",
        "invalid-terminal",
        "transport-teardown",
        "transport-timeout",
        "teardown-timeout",
        "teardown-cancel",
    ],
)
def test_installed_roles_use_admitted_mcp_and_reject_ambient_authority(
    tmp_path, opencode_binary, mode
):
    repo = Path(__file__).resolve().parents[1]
    common = repo / "mcp/aptl-mcp-common"
    assert (common / "build/lilrae-tool-admission.js").is_file(), (
        "build common MCP before qualification"
    )
    node = shutil.which("node")
    assert node, "qualification requires Node"
    installed = install_wheel(tmp_path)
    fixture_root = tmp_path / "fixtures"
    helpers = fixture_root / "tests"
    helpers.mkdir(parents=True)
    (helpers / "__init__.py").write_text("")
    for name in (
        "opencode_fixture.py",
        "lilrae_concurrent_fixture.py",
        "test_lilrae_concurrent_participants.py",
        "test_lilrae_participant_tools.py",
        "lilrae_tool_fixture.py",
    ):
        shutil.copyfile(repo / "tests" / name, helpers / name)
    native = fixture_root / "native"
    native.mkdir()
    (native / "package.json").write_text('{"type":"module"}')
    shutil.copytree(common / "build", native / "build")
    shutil.copytree(common / "node_modules", native / "node_modules", symlinks=True)
    for name in ("admitted-mcp.mjs", "qualify_installed.py"):
        shutil.copyfile(repo / "tests/fixtures/opencode" / name, native / name)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(native / "qualify_installed.py"),
            str(installed),
            str(fixture_root),
            str(opencode_binary),
            node,
            str(native / "admitted-mcp.mjs"),
            str(native / "build/lilrae-tool-admission.js"),
            str(tmp_path / "work"),
            mode,
        ],
        cwd=fixture_root,
        capture_output=True,
        text=True,
        timeout=150,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    observed = json.loads(result.stdout)
    assert observed["roles"] == 2
    assert observed["native_effects"] == (
        2
        if mode in {"authorized", "teardown", "invalid-terminal", "transport-teardown"}
        else 0
    )
    assert observed["isolated"] is True
    if mode in {
        "timeout",
        "cancel",
        "malformed",
        "teardown",
        "invalid-terminal",
        "transport-teardown",
        "transport-timeout",
        "teardown-timeout",
        "teardown-cancel",
    }:
        assert observed["clean_next_trial"] is True
