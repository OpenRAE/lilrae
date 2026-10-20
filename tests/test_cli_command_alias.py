"""Tests for the ``lilrae`` commands and the deprecated ``aptl`` aliases.

Issue #1402 and the ADR-062 successor clause make ``lilrae`` and
``lilrae-misp-suricata-sync`` the primary commands. ``aptl`` and
``aptl-misp-suricata-sync`` stay as aliases until 10.0.0 (#1403). An alias
writes one notice to stderr and leaves stdout and the exit status unchanged.

The subprocess tests run the console scripts that the installed package puts
next to the interpreter, so they exercise the real entry-point metadata.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_REPO = Path(__file__).resolve().parents[1]
_BIN = Path(sys.executable).parent
_SUPPRESS = "LILRAE_SUPPRESS_APTL_DEPRECATION"
_CLI_NOTICE = (
    "warning: the 'aptl' command is deprecated and will be removed in "
    "LilRAE 10.0.0. Use 'lilrae' instead. "
    "Set LILRAE_SUPPRESS_APTL_DEPRECATION=1 to hide this notice."
)
_SYNC_NOTICE = (
    "warning: the 'aptl-misp-suricata-sync' command is deprecated and will be "
    "removed in LilRAE 10.0.0. Use 'lilrae-misp-suricata-sync' instead. "
    "Set LILRAE_SUPPRESS_APTL_DEPRECATION=1 to hide this notice."
)


def _clean_env(**extra: str) -> dict[str, str]:
    """Return a minimal environment without inherited suppression or MISP settings."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": "C.UTF-8",
        "COLUMNS": "100",
        "NO_COLOR": "1",
        "TERM": "dumb",
    }
    env.update(extra)
    return env


def _run(
    command: str, *args: str, cwd: Path | None = None, **env: str
) -> subprocess.CompletedProcess[str]:
    """Run one installed console script and capture its streams separately."""
    executable = _BIN / command
    assert executable.is_file(), f"console script {command!r} is not installed"
    return subprocess.run(
        [str(executable), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=_clean_env(**env),
        timeout=300,
        check=False,
    )


def test_pyproject_declares_primary_commands_and_aliases():
    scripts = tomllib.loads((_REPO / "pyproject.toml").read_text())["project"][
        "scripts"
    ]
    assert scripts["lilrae"] == "aptl.cli.main:app"
    assert scripts["aptl"] == "aptl.cli.main:legacy_main"
    assert (
        scripts["lilrae-misp-suricata-sync"]
        == "aptl.services.misp_suricata_sync.main:main"
    )
    assert (
        scripts["aptl-misp-suricata-sync"]
        == "aptl.services.misp_suricata_sync.main:legacy_main"
    )


def test_primary_command_reports_lilrae_version_without_notice():
    import aptl

    result = _run("lilrae", "--version")
    assert result.returncode == 0
    assert result.stdout == f"lilrae {aptl.__version__}\n"
    assert result.stderr == ""


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(("--version",), id="version"),
        pytest.param(("--help",), id="help"),
        pytest.param(("lab", "--help"), id="subcommand-help"),
        pytest.param(("no-such-command",), id="usage-error"),
    ],
)
def test_alias_matches_primary_stdout_and_exit_and_warns_once(args):
    primary = _run("lilrae", *args)
    legacy = _run("aptl", *args)
    assert legacy.returncode == primary.returncode
    assert legacy.stdout == primary.stdout
    assert legacy.stderr.count("deprecated") == 1
    assert legacy.stderr.startswith(_CLI_NOTICE + "\n")
    assert legacy.stderr[len(_CLI_NOTICE) + 1 :] == primary.stderr


def test_alias_leaves_json_stdout_unchanged(tmp_path):
    (tmp_path / "aptl.json").write_text("{}\n")
    args = ("config", "show", "--json", "--project-dir", str(tmp_path))
    primary = _run("lilrae", *args, cwd=tmp_path)
    legacy = _run("aptl", *args, cwd=tmp_path)
    assert primary.returncode == legacy.returncode == 0
    assert json.loads(legacy.stdout) == json.loads(primary.stdout)
    assert legacy.stdout == primary.stdout
    assert legacy.stderr == _CLI_NOTICE + "\n"


def test_suppression_hides_only_the_notice():
    result = _run("aptl", "--version", **{_SUPPRESS: "1"})
    assert result.returncode == 0
    assert result.stdout.startswith("lilrae ")
    assert result.stderr == ""


@pytest.mark.parametrize("value", ["0", "true", "yes", ""])
def test_other_suppression_values_keep_the_notice(value):
    result = _run("aptl", "--version", **{_SUPPRESS: value})
    assert result.stderr == _CLI_NOTICE + "\n"


def test_sync_alias_warns_once_and_keeps_the_exit_status():
    # No MISP settings: both names fail configuration before any daemon work.
    primary = _run("lilrae-misp-suricata-sync")
    legacy = _run("aptl-misp-suricata-sync")
    assert primary.returncode == legacy.returncode == 2
    assert "deprecated" not in primary.stderr
    assert legacy.stderr.startswith(_SYNC_NOTICE + "\n")
    assert legacy.stderr.count("deprecated") == 1
    assert legacy.stdout == primary.stdout == ""


def test_sync_alias_suppression():
    result = _run("aptl-misp-suricata-sync", **{_SUPPRESS: "1"})
    assert result.returncode == 2
    assert "deprecated" not in result.stderr


def test_alias_warns_on_every_invocation_in_one_interpreter(monkeypatch, capsys):
    """The notice has no process-global "already warned" state."""
    from aptl.cli.main import legacy_main

    monkeypatch.delenv(_SUPPRESS, raising=False)
    monkeypatch.setattr(sys, "argv", ["aptl", "--version"])
    for _ in range(2):
        with pytest.raises(SystemExit) as exit_info:
            legacy_main()
        assert exit_info.value.code in (0, None)
    captured = capsys.readouterr()
    assert captured.err == (_CLI_NOTICE + "\n") * 2
    assert captured.out.count("lilrae ") == 2


def test_primary_app_import_has_no_notice(capsys):
    """Library use of the Typer app never enters the alias boundary."""
    from typer.testing import CliRunner

    from aptl.cli.main import app

    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "deprecated" not in result.output
    assert capsys.readouterr().err == ""


def test_sync_container_enters_through_the_primary_command():
    dockerfile = (_REPO / "containers/misp-suricata-sync/Dockerfile").read_text()
    assert 'ENTRYPOINT ["lilrae-misp-suricata-sync"]' in dockerfile.splitlines()


def test_pack_content_probe_keeps_the_pack_supplied_sync_name():
    """The TechVault pack ships its own frozen sync script named ``aptl-*``."""
    from aptl.core.deployment import _forwarding_agent_realization as realization

    source = Path(realization.__file__).read_text()
    assert 'command -v aptl-misp-suricata-sync' in source
