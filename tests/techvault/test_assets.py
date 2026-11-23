"""The repository ships no copy of TechVault pack-owned scenario content (#1700)."""

from __future__ import annotations

from aptl.core import assets
from tests.test_assets import REPO_ROOT


def test_real_repo_ships_no_techvault_scenario_content_copies() -> None:
    """Pack-owned SDL and exact content do not re-enter APTL's asset tree."""

    tracked_paths = assets._git_tracked(REPO_ROOT)
    assert tracked_paths is not None, "expected a git checkout"
    tracked = {
        path.as_posix() for path in tracked_paths if (REPO_ROOT / path).is_file()
    }
    forbidden = {
        "config/wazuh_cluster/ad_rules.xml",
        "config/wazuh_cluster/custom-shuffle",
        "config/wazuh_cluster/database_rules.xml",
        "config/wazuh_cluster/falco_rules.xml",
        "config/wazuh_cluster/postgresql_decoders.xml",
        "config/wazuh_cluster/samba_decoders.xml",
        "config/wazuh_cluster/suricata_rules.xml",
        "config/wazuh_cluster/webapp_rules.xml",
        "containers/db/init/01-schema.sql",
        "containers/db/init/02-seed-data.sql",
        "containers/dns/named.conf",
        "containers/dns/zones/172.20.rev",
        "containers/dns/zones/techvault.local.zone",
        "containers/fileshare/smb.conf",
        "containers/webapp/app/app.py",
    }

    assert not any(path.startswith("scenarios/") for path in tracked)
    assert tracked.isdisjoint(forbidden)
    assert all(not (REPO_ROOT / path).exists() for path in forbidden)
