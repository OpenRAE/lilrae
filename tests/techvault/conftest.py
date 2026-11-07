"""Released TechVault fixtures for the adapter and released-pack tests (#1700).

Pytest makes these fixtures available only to tests in this directory, so the
collection of a generic test never acquires the released pack.
"""

import pytest


@pytest.fixture(scope="session")
def released_techvault_bundle(tmp_path_factory):
    from aptl.core.scenario_bundle import env_pack_bundle
    from tests.techvault.pack import _pack_root

    bundle = env_pack_bundle(
        tmp_path_factory.mktemp("released-techvault"),
        identity="techvault", source_pack=_pack_root(),
    )
    yield bundle
    bundle.close()


@pytest.fixture(scope="session")
def released_techvault_scenario(released_techvault_bundle):
    """Read-only declarations; tests that alter fields must copy those fields."""
    from raes import parse_sdl_file

    return parse_sdl_file(released_techvault_bundle.sdl_path)


@pytest.fixture(scope="session")
def released_techvault_realization(released_techvault_bundle, released_techvault_scenario):
    """Share the read-only released realization, never a live manager/backend."""
    from tests.techvault.pack import realize_techvault_pack

    return realize_techvault_pack(
        released_techvault_bundle.root, bundle=released_techvault_bundle,
        scenario=released_techvault_scenario,
    )
