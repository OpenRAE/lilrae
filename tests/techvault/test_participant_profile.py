"""The shipped participant profiles bind to TechVault catalog entries (#1700)."""

from __future__ import annotations

from aptl.validation.participant_profile import (
    load_participant_profile,
)
from tests.test_participant_profile import PROFILE_PATH, PROJECT_ROOT


def test_guided_profile_resolves_existing_content_derived_surface() -> None:
    profile = load_participant_profile(PROJECT_ROOT, PROFILE_PATH)

    assert profile.manifest.profile_id == "guided-purple"
    assert profile.manifest.version == 1
    assert profile.manifest.scenario.catalog_id == "techvault-attacker-target"
    assert profile.manifest.capabilities.workbench_profiles == (
        "red",
        "guided-blue",
    )
    assert set(profile.mcp_server_ids) == {
        "aptl-red",
        "aptl-indexer",
        "aptl-wazuh",
    }
    assert set(profile.browser_refs) == {
        "aptl-guide",
        "kali-desktop",
        "soc-wazuh",
    }
    assert (
        profile.manifest.release_evidence.asset_lock_ref
        == "participant-profiles/guided-purple-v1/asset-lock.json"
    )
    assert (
        profile.manifest.release_evidence.qualification_report_ref
        == "release/qualification/guided-purple-v1.json"
    )
    assert profile.manifest.budgets.minimum_hardware.vcpus == 8
    assert profile.manifest.budgets.minimum_hardware.memory_bytes == 16 * 1024**3
    assert set(profile.expected_matrix.selected_profiles) == {
        "kali",
        "victim",
        "wazuh",
    }
    assert "wazuh.manager" in profile.expected_matrix.expected_services
    assert "kali" in profile.expected_matrix.expected_services
    assert "victim" in profile.expected_matrix.expected_services
    assert "suricata" not in profile.expected_matrix.expected_services
    assert "misp" not in profile.expected_matrix.expected_services
    assert "thehive" not in profile.expected_matrix.expected_services
    assert "shuffle-backend" not in profile.expected_matrix.expected_services
    locked_ids = {asset.asset_id for asset in profile.asset_lock.assets}
    assert {
        "raes-scenario",
        "compose-model",
        "mcp-red-build",
        "mcp-indexer-build",
        "mcp-wazuh-build",
        "image-kali",
        "image-victim",
        "image-wazuh-manager",
        "image-wazuh-indexer",
        "image-wazuh-dashboard",
    } <= locked_ids
    assert {
        service
        for asset in profile.asset_lock.assets
        if asset.kind == "oci-image"
        for service in asset.services
    } == set(profile.expected_matrix.expected_services)


def test_only_the_full_acquired_profile_is_a_packaged_lab_asset() -> None:
    from aptl._asset_manifest import ASSET_ROOTS

    assert "participant-profiles/techvault-full-v1" in ASSET_ROOTS
    assert "participant-profiles" not in ASSET_ROOTS
