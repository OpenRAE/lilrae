"""The released TechVault pack's seat image inventory (#1700)."""

from __future__ import annotations

from pathlib import Path

from tests.techvault.pack import PROJECT_ROOT as ROOT


def test_realized_techvault_image_inventory_includes_helpers_and_children(
    tmp_path: Path,
) -> None:
    from aptl.appliance.input_images import canonical_image_references
    from aptl.core.config import AptlConfig
    from aptl.core.scenario_bundle import env_pack_bundle
    from aptl.validation.curated_live_proof import expected_bundle_matrix

    bundle = env_pack_bundle(tmp_path / "packs", "techvault")
    references = canonical_image_references(ROOT, bundle)
    matrix = expected_bundle_matrix(ROOT, AptlConfig(), bundle)

    assert {
        "scenario." + service for service in matrix.expected_services
    } <= references.keys()
    assert references["scenario.ad"].split("/", 1)[0] == "aptl"
    assert references["child.shuffle-worker"].split("/", 1)[0] == "ghcr.io"
    assert references["helper.certs"].split("/", 1)[0] == "wazuh"
    assert "@sha256:" in references["scenario.misp"]
