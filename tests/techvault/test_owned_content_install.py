"""The released TechVault pack installs owned content as its declared owner (#1700)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from aptl.core.deployment import _compose_content_mounts as mounts


@pytest.fixture(scope="module")
def released_owner_mounts(
    tmp_path_factory, released_techvault_bundle, released_techvault_realization
):
    realization = released_techvault_realization
    spec = realization.deployment_spec(sorted(realization.profiles))
    addresses = {
        node.address for node in spec.nodes
        if node.service_name in {"wazuh-manager", "wazuh-dashboard"}
    }
    spec = replace(
        spec,
        nodes=tuple(node for node in spec.nodes if node.address in addresses),
        images=tuple(image for image in spec.images if image.address in addresses),
        content=tuple(item for item in spec.content if item.target_address in addresses),
    )
    return mounts.image_node_content_override(
        spec, released_techvault_bundle.root, tmp_path_factory.mktemp("owner-mounts")
    )


def test_the_released_pack_installs_filebeat_config_as_root(
    released_owner_mounts,
):
    override = released_owner_mounts

    volumes = override["services"]["wazuh-manager"]["volumes"]
    targets = {item["target"]: item["source"] for item in volumes}
    assert "/etc/filebeat/filebeat.yml" not in targets
    manifest = Path(targets[str(mounts.OWNED_CONTENT_MANIFEST)]).read_text()
    assert "0600 root root" in manifest
    assert manifest.rstrip().endswith("/etc/filebeat/filebeat.yml")


def test_the_released_pack_installs_dashboard_config_as_the_image_user(
    released_owner_mounts,
):
    override = released_owner_mounts

    volumes = override["services"]["wazuh-dashboard"]["volumes"]
    targets = {item["target"]: Path(item["source"]) for item in volumes}
    config = "/usr/share/wazuh-dashboard/config/opensearch_dashboards.yml"
    app = "/usr/share/wazuh-dashboard/data/wazuh/config/wazuh.yml"
    assert config not in targets
    assert app not in targets
    manifest = targets[str(mounts.OWNED_CONTENT_MANIFEST)].read_text().splitlines()
    assert sorted(line.split()[-1] for line in manifest) == sorted([config, app])
    for line in manifest:
        mode, owner, group, name, _dest = line.split()
        assert (mode, owner, group) == ("0600", "wazuh-dashboard", "wazuh-dashboard")
        staged = targets[str(mounts.OWNED_CONTENT_ROOT / name)]
        assert staged.stat().st_mode & 0o777 == 0o644
        assert staged.parent.stat().st_mode & 0o777 == 0o700
