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
    monkeypatch.setattr(check, "pack_facts", lambda _pack, **_kwargs: facts)

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


def test_boundary_checker_reads_the_configured_owner_release(check, tmp_path):
    import json
    import shutil
    from aptl.core.scenario_bundle import EnvPackError, env_pack_bundle

    bundle = env_pack_bundle(tmp_path / "acquired", "techvault")
    destination = tmp_path / "releases" / "techvault"
    shutil.copytree(bundle.root, destination)
    bundle.close()
    (tmp_path / "aptl.json").write_text(json.dumps({"scenario": {
        "identity": "techvault", "pack_directory": "releases/techvault",
    }}))
    assert "misp.techvault.local" in check.pack_facts("techvault", project_dir=tmp_path)
    (destination / "assets" / "unmanifested.txt").write_text("corruption")
    with pytest.raises(EnvPackError):
        check.pack_facts("techvault", project_dir=tmp_path)


def test_boundary_check_accepts_explicit_owner_sources(check, tmp_path, monkeypatch):
    from tests.fixture_pack import FIXTURE_PACK_IDENTITY

    monkeypatch.setattr(check, "owner_packs", lambda: {FIXTURE_PACK_IDENTITY})
    found = []

    def observe(pack_id, *, project_dir, pack_directory=None):
        found.append((pack_id, project_dir, pack_directory))
        return {"owned.example.test": "hostname"}

    monkeypatch.setattr(check, "pack_facts", observe)
    assert check.main([
        "check", str(tmp_path), "--pack-directory",
        f"{FIXTURE_PACK_IDENTITY}=releases/{FIXTURE_PACK_IDENTITY}",
    ]) == 0
    assert found == [(FIXTURE_PACK_IDENTITY, tmp_path, f"releases/{FIXTURE_PACK_IDENTITY}")]


def test_missing_owner_source_has_a_value_free_diagnostic(
    check, tmp_path, monkeypatch, capsys,
):
    monkeypatch.setattr(check, "owner_packs", lambda: {"unavailable-owner"})
    assert check.main(["check", str(tmp_path)]) == 1
    assert "Traceback" not in capsys.readouterr().err


def test_project_tree_selection_keeps_installed_owner_packs_checkable(check, tmp_path):
    import json

    (tmp_path / "aptl.json").write_text(json.dumps({"scenario": {
        "source": "project-tree", "identity": "techvault",
    }}))
    assert "misp.techvault.local" in check.pack_facts("techvault", project_dir=tmp_path)


def test_owner_identity_is_a_fact_even_without_authored_hosts(check, monkeypatch):
    from types import SimpleNamespace
    from pathlib import Path
    import tempfile
    bundle = SimpleNamespace(sdl_path=Path('unused'))
    monkeypatch.setattr('aptl.backends._raes_scenario_resolution.resolve_scenario_bundle', lambda *args, **kwargs: bundle)
    monkeypatch.setattr('aptl.backends.raes.parse_sdl_file', lambda *args: SimpleNamespace(nodes={}, accounts={}))
    assert check.pack_facts('different-owner')['different-owner'] == 'pack identifier'


def test_reviewed_exception_does_not_allow_a_new_identifier_line(check, tmp_path):
    import hashlib
    import json
    path = tmp_path / 'src/aptl/compatibility.py'
    path.parent.mkdir(parents=True)
    original = 'LEGACY = "another-owner:old-contract/v1"\n'
    path.write_text(original)
    policy = tmp_path / '.gc/pack-ownership.json'
    policy.parent.mkdir()
    policy.write_text(json.dumps({'schema': 'lilrae-pack-ownership/v1', 'exceptions': [{
        'path': 'src/aptl/compatibility.py', 'owner': 'external_adapter',
        'symbol': 'LEGACY', 'kind': 'pack identifier', 'count': 1,
        'line_digest': 'sha256:' + hashlib.sha256(original.rstrip('\n').encode()).hexdigest(),
        'purpose': 'Preserve one old serialized contract.',
        'allowed_use': 'Only that retained compatibility constant.',
        'retirement': 'Remove with the old contract reader.',
    }]}))
    facts = {'another-owner': 'pack identifier'}
    assert check.findings(tmp_path, facts) == []
    path.write_text(original + 'DEFAULT = "another-owner"\n')
    assert check.findings(tmp_path, facts) == [('src/aptl/compatibility.py', 'pack identifier')]
    path.write_text(original + original)
    assert check.findings(tmp_path, facts) == [('src/aptl/compatibility.py', 'pack identifier')]


def test_owner_path_detects_a_dependency_without_a_pack_literal(check, tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    module = tmp_path / 'src/aptl/backends/fixture_policy.py'
    module.parent.mkdir(parents=True)
    module.write_text('def read_policy():\n    return ()\n')
    (tmp_path / '.gc').mkdir()
    (tmp_path / '.gc/pack-ownership.json').write_text(json.dumps({
        'schema': 'lilrae-pack-ownership/v1', 'exceptions': [],
        'owned_paths': [{'path': 'src/aptl/backends/fixture_policy.py', 'owner_path': 'src/independent_adapter'}],
    }))
    monkeypatch.setattr(check, 'owner_declarations', lambda: {'independent-pack': {'independent_adapter'}})
    monkeypatch.setattr('aptl.backends._raes_scenario_resolution.resolve_scenario_bundle', lambda *args, **kwargs: SimpleNamespace(sdl_path=tmp_path / 'unused'))
    monkeypatch.setattr('aptl.backends.raes.parse_sdl_file', lambda *args: SimpleNamespace(nodes={}, accounts={}))
    facts = check.pack_facts('independent-pack', project_dir=tmp_path)
    caller = tmp_path / 'src/aptl/backends/another.py'
    caller.write_text('from aptl.backends.fixture_policy import read_policy\n')
    assert check.findings(tmp_path, facts) == [('src/aptl/backends/another.py', 'pack identifier')]


def test_the_check_reads_go_source_and_its_pack_identifiers(check, tmp_path):
    """A pack fact or a pack identifier in Go source fails the check (#1553)."""
    facts = {"misp.example.test": "hostname", "examplepack": "pack identifier"}
    surfaces = {
        ("doc.go", "hostname"),
        ("cmd/lilrae/main.go", "hostname"),
        ("internal/core/scenario.go", "pack identifier"),
        ("adapter/api.go", "pack identifier"),
        ("conformance/cli_test.go", "hostname"),
        ("tools/internal/check/check.go", "pack identifier"),
    }
    for relative, kind in surfaces:
        fact = next(value for value, found in facts.items() if found == kind)
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'package x\n\nconst name = "{fact}"\n', encoding="utf-8")
    # A pack identifier outside Go and src/aptl stays out of scope, and the
    # Caddy build is not first-party Go code.
    for relative in ("scripts/run.sh", "web/caddy-build/main.go"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("examplepack\n", encoding="utf-8")

    assert set(check.findings(tmp_path, facts)) == surfaces
