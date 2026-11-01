"""The targeted test runner runs whole Go packages and never a full suite (#1553)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run-targeted-tests.sh"
PLUGINS = ROOT / "tools" / "pytest-plugins"


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "tools" / "internal" / "calc").mkdir(parents=True)
    (repo / "tools" / "go.mod").write_text("module example.com/tools\n\ngo 1.27.0\n", encoding="utf-8")
    (repo / "tools" / "internal" / "calc" / "calc_test.go").write_text("package calc\n", encoding="utf-8")
    (repo / "go.mod").write_text("module example.com/root\n\ngo 1.27.0\n", encoding="utf-8")
    (repo / "root_test.go").write_text("package root\n", encoding="utf-8")
    (repo / "tools" / "internal" / "calc" / "testdata").mkdir()
    (repo / "tools" / "internal" / "calc" / "testdata" / "fixture_test.go").write_text("package x\n", encoding="utf-8")
    (repo / ".ground-control.yaml").write_text("workflow:\n  base_branch: go-cutover\n", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    return repo


def _run(
    repo: Path, tmp_path: Path, *args: str, uv_status: int = 0
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run the runner with stubs that log each go, uv, and git call.

    The uv stub logs PYTHONPATH and exits with uv_status.
    """
    stubs = tmp_path / "bin"
    stubs.mkdir(exist_ok=True)
    log = tmp_path / "calls.log"
    real_git = shutil.which("git")
    assert real_git
    (stubs / "go").write_text(f'#!/bin/sh\nprintf "%s|%s\\n" "$PWD" "$*" >> {log}\n', encoding="utf-8")
    (stubs / "uv").write_text(
        f'#!/bin/sh\nprintf "uv|%s|%s\\n" "$PYTHONPATH" "$*" >> {log}\nexit {uv_status}\n', encoding="utf-8"
    )
    (stubs / "git").write_text(f'#!/bin/sh\nprintf "git|%s\\n" "$*" >> {log}\nexec {real_git} "$@"\n', encoding="utf-8")
    for stub in stubs.iterdir():
        stub.chmod(0o700)
    env = {**os.environ, "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}"}
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        ["bash", str(RUNNER), *args], cwd=repo, env=env, capture_output=True, text=True, check=False
    )
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return result, calls


def test_changed_go_test_files_run_their_whole_packages_from_each_module(tmp_path):
    repo = _repo(tmp_path)

    result, calls = _run(repo, tmp_path)

    assert result.returncode == 0, result.stderr
    go_calls = sorted(call for call in calls if not call.startswith("git|"))
    assert go_calls == [
        f"{repo}/tools|test -race -shuffle=on ./internal/calc",
        f"{repo}|test -race -shuffle=on ./",
    ]
    # The diff base comes from .ground-control.yaml, not a fixed origin/dev.
    assert any("origin/go-cutover...HEAD" in call for call in calls)


def test_explicit_go_test_files_run_without_a_python_suite(tmp_path):
    repo = _repo(tmp_path)

    result, calls = _run(repo, tmp_path, "tools/internal/calc/calc_test.go")

    assert result.returncode == 0, result.stderr
    assert [call for call in calls if not call.startswith("git|")] == [
        f"{repo}/tools|test -race -shuffle=on ./internal/calc"
    ]


def test_a_go_test_file_without_a_module_is_an_error(tmp_path):
    repo = _repo(tmp_path)
    (repo / "go.mod").unlink()
    (repo / "loose").mkdir()
    (repo / "loose" / "loose_test.go").write_text("package loose\n", encoding="utf-8")

    result, _calls = _run(repo, tmp_path, "loose/loose_test.go")

    assert result.returncode == 2
    assert "No go.mod above loose/loose_test.go." in result.stderr


def test_a_stopped_pytest_run_runs_no_go_test(tmp_path):
    """The plugin decides whether pytest has a target; its stop ends the run (#1583)."""
    repo = _repo(tmp_path)

    result, calls = _run(repo, tmp_path, "tools/internal/calc/calc_test.go", "--ignore", "tests/test_calc.py", uv_status=4)

    assert result.returncode == 4
    assert [call for call in calls if not call.startswith("git|")] == [
        f"uv|{PLUGINS}|run --group build --no-default-groups --extra dev --extra web"
        " pytest -p require_test_targets --ignore tests/test_calc.py",
    ]


def test_python_targets_run_pytest_with_their_arguments(tmp_path):
    repo = _repo(tmp_path)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_calc.py").write_text("def test_calc():\n    pass\n", encoding="utf-8")

    result, calls = _run(repo, tmp_path, "tools/internal/calc/calc_test.go", "tests/test_calc.py::test_calc", "-v")

    assert result.returncode == 0, result.stderr
    assert [call for call in calls if not call.startswith("git|")] == [
        f"uv|{PLUGINS}|run --group build --no-default-groups --extra dev --extra web"
        " pytest -p require_test_targets tests/test_calc.py::test_calc -v",
        f"{repo}/tools|test -race -shuffle=on ./internal/calc",
    ]


def test_the_plugin_stops_a_run_without_a_test_file(pytester: pytest.Pytester) -> None:
    """pytest decides which arguments are targets, so an option value never counts (#1583)."""
    pytester.makepyfile(test_a="def test_a():\n    pass\n")
    pytester.makeini("[pytest]\ntestpaths = .\n")
    pytester.syspathinsert(PLUGINS)
    stopped = (
        ("--ignore", "test_a.py"),
        ("--deselect", "test_a.py::test_a"),
        ("-k", "test_a"),
        ("--rootdir", str(pytester.path)),
        (str(pytester.path),),
        ("missing.py",),
    )

    for args in stopped:
        result = pytester.runpytest("-p", "require_test_targets", *args)

        assert result.ret == pytest.ExitCode.USAGE_ERROR, args
        assert "the full suite runs only in CI" in result.stderr.str(), args

    result = pytester.runpytest("-p", "require_test_targets", "test_a.py::test_a", "-k", "test_a")
    assert result.ret == pytest.ExitCode.OK
