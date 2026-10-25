"""Dashboard config delivery, proved in the pinned Wazuh Dashboard image (#1422).

The unit tests prove the staging and the manifest. These tests answer what they
cannot: can the image's own non-root user read the declared config, and is the
declared ``wazuh.yml`` still valid YAML after the image's app-config step?

The staged files get a foreign host owner first. A host uid that equals the
image user's uid (1000) hides the defect, so the tests must not depend on it.

Marked ``integration`` per test, and skipped when the daemon or the pinned image
is unavailable.
"""

from __future__ import annotations

import secrets
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from aptl.backends._raes_backend_implementation_catalog import (
    _DASHBOARD_START,
    BACKEND_IMPLEMENTATION_PROFILES,
)
from aptl.core.deployment import _compose_content_mounts as mounts
from aptl.core.deployment.realization import (
    DeploymentContentRealization,
    DeploymentImageRealization,
    DeploymentNodeRealization,
    DeploymentRealizationSpec,
)

_PROFILE = next(
    item
    for item in BACKEND_IMPLEMENTATION_PROFILES
    if item.profile_id == "wazuh-dashboard-4.12"
)
_IMAGE = _PROFILE.image_ref
_CONFIG = "/usr/share/wazuh-dashboard/config/opensearch_dashboards.yml"
_APP = "/usr/share/wazuh-dashboard/data/wazuh/config/wazuh.yml"
_APP_TEXT = (
    "hosts:\n"
    "  - default:\n"
    '      url: "https://wazuh-manager"\n'
    "      port: 55000\n"
    "      username: wazuh-wui\n"
    '      password: "fixture"\n'
    "      run_as: false\n"
)
_FOREIGN_OWNER = "4242:4242"
# The start steps refuse an unset indexer login. These tests never reach the
# indexer, so a random value per run serves.
_LOGIN_ENV = [
    "-e",
    f"DASHBOARD_USERNAME=user-{secrets.token_hex(4)}",
    "-e",
    f"DASHBOARD_PASSWORD={secrets.token_hex(16)}",
]


def _docker(*args: str, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout
    )


def _image_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return _docker("image", "inspect", _IMAGE, timeout=60).returncode == 0


requires_image = pytest.mark.skipif(
    not _image_available(), reason=f"needs a Docker daemon with {_IMAGE}"
)


def _content(name: str, dest: str, text: str) -> DeploymentContentRealization:
    return DeploymentContentRealization(
        address=f"provision.content-placement.{name}",
        target_address="provision.node.wazuh-dashboard",
        content_name=name,
        volume_suffix="",
        dest_relpath=dest,
        source_kind="inline-text",
        inline_text=text,
        sensitive=True,
    )


def _owned(path: str) -> SimpleNamespace:
    return SimpleNamespace(
        path=path,
        owner_user="wazuh-dashboard",
        owner_group="wazuh-dashboard",
        mode="0600",
    )


def _dashboard_override(engine: Path) -> list[dict[str, object]]:
    """Stage both configs through the real content-mount path."""

    runtime = SimpleNamespace(
        container=SimpleNamespace(
            entrypoint=_PROFILE.runtime_selections["runtime-container-entrypoint"]
        ),
        filesystem_inventory=[_owned(_CONFIG), _owned(_APP)],
    )
    spec = DeploymentRealizationSpec(
        profiles=(),
        nodes=(
            DeploymentNodeRealization(
                address="provision.node.wazuh-dashboard",
                name="wazuh-dashboard",
                service_name="wazuh-dashboard",
                container_name="aptl-wazuh-dashboard",
                networks=(),
                runtime=runtime,
            ),
        ),
        networks=(),
        images=(
            DeploymentImageRealization(
                address="provision.node.wazuh-dashboard",
                service_name="wazuh-dashboard",
                source_name=_PROFILE.source_name,
                source_version=_PROFILE.source_version,
                image_ref=_IMAGE,
                mode="pull",
                policy_rule="backend-open-profile",
            ),
        ),
        content=(
            _content("opensearch-config", _CONFIG, "server.host: 0.0.0.0\n"),
            _content("app-config", _APP, _APP_TEXT),
        ),
    )
    override = mounts.image_node_content_override(spec, engine / "pack", engine)
    return override["services"]["wazuh-dashboard"]["volumes"]


def _give_foreign_owner(directory: Path) -> None:
    """Give every file in *directory* a host owner that is not uid 1000."""

    result = _docker(
        "run", "--rm", "--network", "none", "--user", "0",
        "--entrypoint", "/bin/sh", "-v", f"{directory}:/staged", _IMAGE,
        "-c", f"chown {_FOREIGN_OWNER} /staged/*",
    )  # fmt: skip
    assert result.returncode == 0, result.stderr


def _run(volumes: list[dict[str, object]], script: str) -> subprocess.CompletedProcess:
    mounts_args: list[str] = []
    for volume in volumes:
        mounts_args += ["-v", f"{volume['source']}:{volume['target']}:ro"]
    return _docker(
        "run", "--rm", "--network", "none", *_LOGIN_ENV, *mounts_args,
        "--entrypoint", "/bin/sh", _IMAGE, "-ec", script,
    )  # fmt: skip


@pytest.mark.integration
@requires_image
def test_a_foreign_owned_0600_bind_is_unreadable_by_the_image_user(tmp_path):
    staged = tmp_path / "direct"
    staged.mkdir(mode=0o700)
    (staged / "opensearch_dashboards.yml").write_text("server.host: 0.0.0.0\n")
    (staged / "opensearch_dashboards.yml").chmod(0o600)
    _give_foreign_owner(staged)

    result = _run(
        [{"source": staged / "opensearch_dashboards.yml", "target": _CONFIG}],
        f"cat {_CONFIG}",
    )

    assert result.returncode != 0
    assert "Permission denied" in result.stderr


@pytest.mark.integration
@requires_image
def test_the_image_user_installs_declared_config_it_can_read(tmp_path):
    volumes = _dashboard_override(tmp_path / "engine")
    _give_foreign_owner(Path(str(volumes[0]["source"])).parent)
    # The profile's own start steps, up to the keystore and server start.
    start = _DASHBOARD_START.split("; yes |", 1)[0]
    parse = (
        "cd /usr/share/wazuh-dashboard && node/bin/node -e "
        '\'require("js-yaml").load(require("fs")'
        f'.readFileSync("{_APP}", "utf8"))\''
    )

    result = _run(
        volumes,
        f"{start}; {parse}; stat -c '%U:%G:%a' {_CONFIG} {_APP}; cat {_CONFIG} {_APP}",
    )

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines(keepends=True)
    assert lines[:2] == ["wazuh-dashboard:wazuh-dashboard:600\n"] * 2
    # The image user read both files, and declared content wrote wazuh.yml last.
    assert "".join(lines[2:]) == "server.host: 0.0.0.0\n" + _APP_TEXT


@pytest.mark.integration
@requires_image
def test_a_restart_with_retained_state_reinstalls_declared_config(tmp_path):
    volumes = _dashboard_override(tmp_path / "engine")
    _give_foreign_owner(Path(str(volumes[0]["source"])).parent)
    start = _DASHBOARD_START.split("; yes |", 1)[0]
    name = f"aptl-1422-restart-{tmp_path.name}"[:63]
    mounts_args: list[str] = []
    for volume in volumes:
        mounts_args += ["-v", f"{volume['source']}:{volume['target']}:ro"]
    created = _docker(
        "create", "--name", name, "--network", "none", *_LOGIN_ENV, *mounts_args,
        "--entrypoint", "/bin/sh", _IMAGE, "-ec",
        f"{start}; stat -c '%U:%G:%a' {_CONFIG} {_APP}; cat {_APP}",
    )  # fmt: skip
    assert created.returncode == 0, created.stderr
    try:
        # The second start keeps the container filesystem, so both declared
        # files already exist, owned by the image user, when the steps rerun.
        runs = [_docker("start", "-a", name) for _ in range(2)]
    finally:
        _docker("rm", "-f", name)

    expected = "wazuh-dashboard:wazuh-dashboard:600\n" * 2 + _APP_TEXT
    for run in runs:
        assert run.returncode == 0, run.stderr
        assert run.stdout == expected
