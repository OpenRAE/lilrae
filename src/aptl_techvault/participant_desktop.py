"""What the TechVault participant desktop opens, lists, and resolves.

These are references into the TechVault pack: SDL node and service names for
the SOC consoles in tab order, SDL account credentials for their logins, the
pack's participant guide, and the node whose authored hostname the browser must
resolve. Core reads every URL, address, hostname, and credential value from the
admitted SDL and the realized lab.
"""

from __future__ import annotations

from aptl.backends.participant_desktop import (
    EXTENSION_API_VERSION,
    DesktopConsole,
    DesktopCredential,
    ParticipantDesktopSpec,
)
from aptl.core.scenario_bundle import ScenarioBundle

from aptl_techvault.pack_identity import (
    TECHVAULT_PACK_SET_DIGEST,
    TECHVAULT_PACK_VERSION,
)

TECHVAULT_DESKTOP = ParticipantDesktopSpec(
    consoles=(
        DesktopConsole("Wazuh", "wazuh-dashboard", "dashboard"),
        DesktopConsole("TheHive", "thehive", "thehive-api"),
        DesktopConsole("Cortex", "cortex", "cortex-api"),
        DesktopConsole("Shuffle", "shuffle-frontend", "https"),
        DesktopConsole("MISP", "misp", "https"),
    ),
    credentials=(
        DesktopCredential("Wazuh", "wazuh-indexer-admin", "wazuh-indexer-admin-primary"),
        DesktopCredential(
            "TheHive", "thehive-administrator", "thehive-administrator-primary"
        ),
        DesktopCredential(
            "Cortex", "cortex-administrator", "cortex-administrator-primary"
        ),
        DesktopCredential(
            "Shuffle", "shuffle-administrator", "shuffle-administrator-primary"
        ),
        DesktopCredential("MISP", "misp-administrator", "misp-administrator-primary"),
    ),
    guide="docs/attack-path.md",
    hostnames=("misp",),
)


class TechVaultParticipantDesktop:
    """Bind the TechVault desktop references to the exact qualified pack."""

    extension_api_version = EXTENSION_API_VERSION
    supported_pack_id = "techvault"
    supported_pack_versions = (TECHVAULT_PACK_VERSION,)
    supported_pack_set_digests = (TECHVAULT_PACK_SET_DIGEST,)

    @staticmethod
    def resolve(bundle: ScenarioBundle) -> ParticipantDesktopSpec:
        return TECHVAULT_DESKTOP


provider = TechVaultParticipantDesktop()


__all__ = ("TECHVAULT_DESKTOP", "TechVaultParticipantDesktop", "provider")
