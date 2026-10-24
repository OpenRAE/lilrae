"""The pack boundary check fails the build on a pack-owned fact (#1121, #1273).

The owners and their facts come from installed adapters and their packs' SDL,
not from a list in the check. These tests run the check over this repository
and over a copy with one planted fact of each kind.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _check():
    path = ROOT / "tools" / "check_pack_boundary.py"
    spec = importlib.util.spec_from_file_location("check_pack_boundary", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def check():
    return _check()


@pytest.fixture(scope="module")
def facts(check):
    owners = check.owner_packs()
    assert {"techvault", "techvault-participant-study"} <= owners
    collected = {}
    for pack_id in sorted(owners):
        collected.update(check.pack_facts(pack_id))
    return collected


def test_the_owner_facts_come_from_the_pack_sdl(facts):
    kinds = set(facts.values())

    assert {"hostname", "credential", "account username"} <= kinds
    assert "misp.techvault.local" in facts


def test_the_covered_generic_paths_carry_no_pack_fact(check, facts):
    assert check.findings(ROOT, facts) == []


@pytest.mark.parametrize("kind", ["hostname", "credential", "account username"])
def test_a_planted_fact_fails_the_check(check, facts, kind, tmp_path):
    fact = next(value for value, found in sorted(facts.items()) if found == kind)
    target = tmp_path / "scripts" / "launch.sh"
    target.parent.mkdir(parents=True)
    target.write_text(f"#!/bin/sh\necho {fact}\n", encoding="utf-8")

    assert check.findings(tmp_path, facts) == [("scripts/launch.sh", kind)]


def test_the_check_covers_every_issue_surface(check, tmp_path):
    surfaces = {
        "scripts/x.sh",
        "appliance/guest/x.py",
        "mcp/mcp-wazuh/docker-lab-config.json",
        "src/aptl/core/participant_desktop.py",
        "src/aptl/cli/another_surface.py",
        "src/aptl/backends/another_surface.py",
    }
    for relative in surfaces:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("misp.example.test\n", encoding="utf-8")

    found = check.findings(tmp_path, {"misp.example.test": "hostname"})
    assert {path for path, _kind in found} == surfaces


def test_the_cli_reports_kind_and_path_only(check, facts, tmp_path, monkeypatch, capsys):
    secret = next(value for value, kind in facts.items() if kind == "credential")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "x.sh").write_text(secret, encoding="utf-8")
    monkeypatch.setattr(check, "pack_facts", lambda _pack: facts)

    assert check.main(["check", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "scripts/x.sh: carries a pack-owned credential" in err
    assert secret not in err


def test_the_check_fails_closed_without_an_owner(check, tmp_path, monkeypatch):
    monkeypatch.setattr(check, "owner_packs", lambda: set())

    assert check.main(["check", str(tmp_path)]) == 1


def test_staged_hook_runs_the_same_boundary_checker():
    import yaml

    configuration = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())
    hooks = [hook for repo in configuration["repos"] for hook in repo["hooks"]]
    hook = next((hook for hook in hooks if hook["id"] == "lilrae-pack-boundary"), None)

    assert hook is not None
    assert "tools/check_pack_boundary.py" in hook["entry"]
    assert hook["pass_filenames"] is False
