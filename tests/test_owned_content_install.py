"""Owner-declared content reaches an image node with its declared owner (#1273).

A bind mount keeps the host owner. The TechVault pack authors Filebeat's config
as a root-owned 0600 file, and Filebeat refuses any other owner, so a node whose
selected entrypoint runs the owned-content installer gets that file staged and
installed with the owner and mode its SDL inventory declares.
"""

from __future__ import annotations

import sys
from dataclasses import replace
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


# --- Non-root image users (#1422) -------------------------------------------
#
# The Wazuh Dashboard image runs as ``wazuh-dashboard`` and the pack authors its
# config files as ``wazuh-dashboard``-owned 0600 files. A 0600 bind mount keeps
# the host owner, so any host uid other than the image user's gets EACCES. The
# root installer cannot run there, so such a profile selects the image-user
# installer, which installs each file as the image user from a staged copy that
# the image user can read.

_USER_INSTALLER = [
    "/bin/sh",
    "-ec",
    f'{mounts.OWNED_CONTENT_IMAGE_USER_INSTALLER}; exec /entrypoint.sh "$@"',
    "--",
]


def _sensitive_spec(entrypoint, inventory):
    spec = _spec(entrypoint, inventory)
    return replace(spec, content=(replace(spec.content[0], sensitive=True),))


def test_the_installers_are_distinct_so_each_is_detected_alone():
    assert mounts.OWNED_CONTENT_INSTALLER not in (
        mounts.OWNED_CONTENT_IMAGE_USER_INSTALLER
    )
    assert mounts.OWNED_CONTENT_IMAGE_USER_INSTALLER not in (
        mounts.OWNED_CONTENT_INSTALLER
    )


def test_image_user_content_is_staged_readable_inside_an_owner_only_dir(tmp_path):
    entry = _entry(owner_user="app", owner_group="app")
    override = mounts.image_node_content_override(
        _sensitive_spec(_USER_INSTALLER, [entry]),
        tmp_path / "pack",
        tmp_path / "engine",
    )

    targets = {
        item["target"]: Path(item["source"])
        for item in override["services"]["app"]["volumes"]
    }
    assert "/etc/app/app.yml" not in targets
    staged = targets[str(mounts.OWNED_CONTENT_ROOT / "000")]
    # The image user must read the staged copy across the bind mount; the
    # owner-only directory keeps it from other host users.
    assert staged.stat().st_mode & 0o777 == 0o644
    assert staged.parent.stat().st_mode & 0o777 == 0o700
    assert staged.read_text() == "key: value\n"
    manifest = targets[str(mounts.OWNED_CONTENT_MANIFEST)]
    assert manifest.parent == staged.parent
    assert manifest.read_text() == "0600 app app 000 /etc/app/app.yml\n"


def test_root_installed_sensitive_content_stays_owner_only(tmp_path):
    override = mounts.image_node_content_override(
        _sensitive_spec(_INSTALLER, [_entry()]),
        tmp_path / "pack",
        tmp_path / "engine",
    )

    targets = {
        item["target"]: Path(item["source"])
        for item in override["services"]["app"]["volumes"]
    }
    assert targets[str(mounts.OWNED_CONTENT_ROOT / "000")].stat().st_mode & 0o777 == (
        0o600
    )


def _run_user_installer(tmp_path, owner, group):
    """Run the image-user installer with its fixed paths moved under tmp_path."""

    import grp
    import os
    import pwd
    import subprocess

    root = tmp_path / "owned"
    root.mkdir()
    (root / "000").write_text("secret: 1\n")
    dest = tmp_path / "dest" / "app.yml"
    owner = owner or pwd.getpwuid(os.getuid()).pw_name
    group = group or grp.getgrgid(os.getgid()).gr_name
    (root / "manifest").write_text(f"0600 {owner} {group} 000 {dest}\n")
    script = mounts.OWNED_CONTENT_IMAGE_USER_INSTALLER.replace(
        str(mounts.OWNED_CONTENT_ROOT), str(root)
    )
    return dest, subprocess.run(
        ["/bin/sh", "-ec", script], capture_output=True, text=True, timeout=30
    )


# The installer runs in Linux images with GNU ``install``. BSD ``install`` (the
# macOS host) has no ``-D``, so the success path runs only on a Linux host. The
# refusal path exits before ``install`` and runs everywhere.
@pytest.mark.skipif(
    sys.platform != "linux", reason="the installer needs GNU install (-D)"
)
def test_the_image_user_installer_installs_with_the_declared_mode(tmp_path):
    dest, result = _run_user_installer(tmp_path, None, None)

    assert result.returncode == 0, result.stderr
    assert dest.read_text() == "secret: 1\n"
    assert dest.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    ("owner", "group"), [("nobody-else", None), (None, "nobody-else")]
)
def test_the_image_user_installer_refuses_an_owner_it_cannot_give(
    tmp_path, owner, group
):
    dest, result = _run_user_installer(tmp_path, owner, group)

    assert result.returncode != 0
    assert "nobody-else" in result.stderr
    assert not dest.exists()


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


def test_the_dashboard_profile_installs_declared_config_after_app_config():
    from aptl.backends._raes_backend_implementation_catalog import (
        BACKEND_IMPLEMENTATION_PROFILES,
    )

    profile = next(
        item
        for item in BACKEND_IMPLEMENTATION_PROFILES
        if item.profile_id == "wazuh-dashboard-4.12"
    )
    selections = profile.runtime_selections
    shell, flags, script = selections["runtime-container-entrypoint"]
    assert (shell, flags) == ("/bin/sh", "-ec")
    app_config = script.index("/wazuh_app_config.sh")
    install = script.index(mounts.OWNED_CONTENT_IMAGE_USER_INSTALLER)
    server = script.index("exec /usr/share/wazuh-dashboard/bin/opensearch-dashboards")
    # The image's app-config step rewrites a writable wazuh.yml, so declared
    # content is installed after it and before the server reads its config.
    assert app_config < install < server
    assert mounts.OWNED_CONTENT_INSTALLER not in script
    # The fix adds no privilege: no root user, capability, or security option.
    assert not {"linux-capabilities", "runtime-container-privileged"} & set(selections)


@pytest.mark.parametrize("unset", ["DASHBOARD_USERNAME", "DASHBOARD_PASSWORD"])
def test_the_dashboard_start_refuses_an_unset_indexer_login(unset):
    import secrets
    import subprocess

    from aptl.backends._raes_wazuh_dashboard_implementation_catalog import (
        DASHBOARD_START,
    )

    env = {
        "PATH": "/usr/bin:/bin",
        "DASHBOARD_USERNAME": "user",
        "DASHBOARD_PASSWORD": secrets.token_hex(8),
    }
    env.pop(unset)
    # The login check is the first step, before any image script runs.
    check = DASHBOARD_START.split("; ", 1)[0]
    result = subprocess.run(
        ["/bin/sh", "-ec", f"{check}; echo started"],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert result.returncode != 0
    assert unset in result.stderr
    assert "started" not in result.stdout
