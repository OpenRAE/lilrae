"""Owner-declared content reaches an image node with its declared owner (#1273).

A bind mount keeps the host owner. The TechVault pack authors Filebeat's config
as a root-owned 0600 file, and Filebeat refuses any other owner, so a node whose
selected entrypoint runs the owned-content installer gets that file staged and
installed with the owner and mode its SDL inventory declares.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from aptl.core.deployment import _compose_content_mounts as mounts
from aptl.core.deployment.realization import (
    DeploymentContentRealization,
    DeploymentImageRealization,
    DeploymentNodeRealization,
    DeploymentRealizationSpec,
)


def _spec(entrypoint, inventory, dest="/etc/app/app.yml"):
    runtime = SimpleNamespace(
        container=SimpleNamespace(entrypoint=entrypoint),
        filesystem_inventory=inventory,
    )
    return DeploymentRealizationSpec(
        profiles=(),
        nodes=(
            DeploymentNodeRealization(
                address="provision.node.app",
                name="app",
                service_name="app",
                container_name="aptl-app",
                networks=(),
                runtime=runtime,
            ),
        ),
        networks=(),
        images=(
            DeploymentImageRealization(
                address="provision.node.app",
                service_name="app",
                source_name="app",
                source_version="1",
                image_ref="app:1",
                mode="pull",
                policy_rule="allowed-source",
            ),
        ),
        content=(
            DeploymentContentRealization(
                address="provision.content-placement.app-config",
                target_address="provision.node.app",
                content_name="app-config",
                volume_suffix="",
                dest_relpath=dest,
                source_kind="inline-text",
                inline_text="key: value\n",
            ),
        ),
    )


def _entry(**values):
    return SimpleNamespace(
        **{
            "path": "/etc/app/app.yml",
            "owner_user": "root",
            "owner_group": "root",
            "mode": "0600",
            **values,
        }
    )


_INSTALLER = ["/bin/sh", "-ec", f"{mounts.OWNED_CONTENT_INSTALLER}; exec /init"]


def test_owner_declared_content_is_staged_and_listed_for_install(tmp_path):
    override = mounts.image_node_content_override(
        _spec(_INSTALLER, [_entry()]), tmp_path / "pack", tmp_path / "engine"
    )

    targets = {
        item["target"]: item["source"]
        for item in override["services"]["app"]["volumes"]
    }
    assert "/etc/app/app.yml" not in targets
    assert targets[str(mounts.OWNED_CONTENT_ROOT / "000")].endswith("app.yml")
    manifest = Path(targets[str(mounts.OWNED_CONTENT_MANIFEST)]).read_text()
    assert manifest == "0600 root root 000 /etc/app/app.yml\n"


def test_a_node_without_the_installer_keeps_the_bind_mount(tmp_path):
    override = mounts.image_node_content_override(
        _spec(["/init"], [_entry()]), tmp_path / "pack", tmp_path / "engine"
    )

    targets = [item["target"] for item in override["services"]["app"]["volumes"]]
    assert targets == ["/etc/app/app.yml"]


@pytest.mark.parametrize(
    "inventory",
    [
        [_entry(path="/etc/other.yml")],
        [_entry(owner_user=None, owner_group=None, mode=None)],
    ],
)
def test_content_without_a_declared_owner_keeps_the_bind_mount(tmp_path, inventory):
    override = mounts.image_node_content_override(
        _spec(_INSTALLER, inventory),
        tmp_path / "pack",
        tmp_path / "engine",
    )

    targets = [item["target"] for item in override["services"]["app"]["volumes"]]
    assert targets == ["/etc/app/app.yml"]


@pytest.mark.parametrize(
    "entry",
    [
        _entry(owner_user="root; rm -rf /"),
        _entry(mode="u+rw"),
        _entry(owner_group="a b"),
    ],
)
def test_an_unsafe_declared_owner_or_mode_is_refused(tmp_path, entry):
    spec = _spec(_INSTALLER, [entry])
    pack, engine = tmp_path / "pack", tmp_path / "engine"
    with pytest.raises(ValueError):
        mounts.image_node_content_override(spec, pack, engine)


def test_the_released_pack_installs_filebeat_config_as_root(tmp_path):
    from tests.techvault_pack import _pack_root, realize_techvault_pack

    from aptl.core.scenario_bundle import env_pack_bundle

    realization = realize_techvault_pack(tmp_path / "plan")
    spec = realization.deployment_spec(sorted(realization.profiles))
    bundle = env_pack_bundle(tmp_path / "staged", "techvault", source_pack=_pack_root())
    override = mounts.image_node_content_override(
        spec, bundle.root, tmp_path / "engine"
    )

    volumes = override["services"]["wazuh-manager"]["volumes"]
    targets = {item["target"]: item["source"] for item in volumes}
    assert "/etc/filebeat/filebeat.yml" not in targets
    manifest = Path(targets[str(mounts.OWNED_CONTENT_MANIFEST)]).read_text()
    assert "0600 root root" in manifest
    assert manifest.rstrip().endswith("/etc/filebeat/filebeat.yml")
