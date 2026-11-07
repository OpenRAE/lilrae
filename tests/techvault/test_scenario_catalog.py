"""The repository catalog projects the TechVault study pack (#1700)."""

from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def repository_catalog():
    from aptl.core.scenario_catalog import load_scenario_catalog

    with load_scenario_catalog(Path(__file__).resolve().parents[2]) as catalog:
        yield catalog


def test_repository_catalog_projects_validated_pack_identity(repository_catalog):
    catalog = repository_catalog

    assert [entry.id for entry in catalog.scenarios] == [
        "techvault-participant-study"
    ]
    assert catalog.pack_identity.pack_id == "techvault-participant-study"
    assert catalog.pack_identity.pack_version == "7.2.4"
    assert catalog.pack_identity.set_digest.startswith("sha256:")
    assert catalog.maturity == "built"
    assert not hasattr(catalog.scenarios[0], "path")


def test_resolve_acquired_scenario_returns_same_validated_bundle(repository_catalog):
    from aptl.core.scenario_catalog import (
        resolve_acquired_scenario,
    )

    project_root = Path(__file__).resolve().parents[2]
    catalog = repository_catalog
    resolved = resolve_acquired_scenario(
        project_root, "techvault-participant-study", catalog=catalog
    )

    assert resolved.entry.id == "techvault-participant-study"
    assert resolved.scenario.name == "techvault-participant-study"
    assert resolved.bundle is catalog.bundle
