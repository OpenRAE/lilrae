"""The TechVault participant desktop provider and its references (#1700)."""

from __future__ import annotations

from aptl.backends import participant_desktop as seam
from aptl.core import participant_desktop as desktop


def test_the_techvault_provider_supplies_every_field():
    from aptl_techvault.participant_desktop import TECHVAULT_DESKTOP

    spec = seam.validated_spec(TECHVAULT_DESKTOP)

    assert [item.label for item in spec.consoles] == [
        "Wazuh",
        "Shuffle",
        "MISP",
    ]
    assert {item.account for item in spec.credentials} == {
        "wazuh-indexer-admin",
        "shuffle-administrator",
        "misp-administrator",
    }
    assert spec.guide == "docs/attack-path.md"
    assert spec.hostnames == ("misp",)


def test_the_techvault_references_resolve_against_the_released_pack(tmp_path):
    from aptl.backends.raes_declared_credentials import scenario_accounts
    from aptl.core.scenario_bundle import env_pack_bundle
    from aptl_techvault.participant_desktop import TECHVAULT_DESKTOP
    from tests.techvault.pack import _pack_root

    bundle = env_pack_bundle(tmp_path, identity="techvault", source_pack=_pack_root())
    accounts = scenario_accounts(bundle.sdl_path)
    for item in TECHVAULT_DESKTOP.credentials:
        desktop._login(accounts, item)
    assert bundle.read_asset(TECHVAULT_DESKTOP.guide)
    assert seam.select_participant_desktop(bundle) == TECHVAULT_DESKTOP
