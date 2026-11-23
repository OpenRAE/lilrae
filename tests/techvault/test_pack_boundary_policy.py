"""The boundary check reads the installed TechVault owner (#1121, #1700)."""

from __future__ import annotations

import pytest

from tests.test_pack_boundary_policy import check, facts


def test_the_owner_facts_come_from_the_pack_sdl(facts):
    kinds = set(facts.values())

    assert {"hostname", "credential", "account username"} <= kinds
    assert "misp.techvault.local" in facts


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


def test_project_tree_selection_keeps_installed_owner_packs_checkable(check, tmp_path):
    import json

    (tmp_path / "aptl.json").write_text(json.dumps({"scenario": {
        "source": "project-tree", "identity": "techvault",
    }}))
    assert "misp.techvault.local" in check.pack_facts("techvault", project_dir=tmp_path)
