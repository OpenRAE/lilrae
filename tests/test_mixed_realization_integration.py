"""Full-stack real-Docker test: base-container-materialized and image-backed nodes together.

TechVault's real shape is permanently mixed: some nodes convert to the
generic materializer (`runtime:`), others stay on a declared vendor
`source:` (a legitimate, transparently-declared upstream image - not a
hidden appliance image ADR-047/048 targets). `realize()` must materialize
the runtime: subset directly and start the source: subset via Compose, in
one `aptl lab start`, without either side conflicting with or silently
skipping the other.

Constructs the realization spec directly rather than through the RAES
compiler (already proven separately, e.g. test_base_container_admission_
integration.py) so this test isolates `realize()`'s own dispatch.

Marked `integration`; skipped without Docker.
"""

from __future__ import annotations

import shutil
import subprocess
import time

import pytest
from raes.runtime_configuration import RuntimeConfiguration, RuntimePackage

from aptl.core.deployment import (
    DeploymentImageRealization,
    DeploymentNetworkAttachment,
    DeploymentNetworkRealization,
    DeploymentNodeRealization,
    DeploymentRealizationSpec,
    DockerComposeBackend,
)
from tests.helpers import realized_container_name, realized_project_name

pytestmark = pytest.mark.integration


def _materialized_project(tmp_path):
    """Give a test the container assets the generic base images build from.

    Those images build from Dockerfiles under the project directory, which a
    real project has because `aptl lab init` materializes them. A bare
    tmp_path has none, so the build fails on a missing context rather than on
    anything the test is about. Only the container tree is copied: writing a
    whole project would also install a Compose model the spec under test does
    not describe.
    """
    import shutil

    from aptl.core.assets import resolve_asset_source

    source, _ = resolve_asset_source()
    # The generic base Dockerfiles copy from these two trees; the build
    # context is the project root, so both have to be present.
    for tree in ("containers", "requirements"):
        shutil.copytree(source / tree, tmp_path / tree, dirs_exist_ok=True)
    return tmp_path


# The image node's source must serve with no environment: a root
# `docker-compose.yml` is never a scenario realization input (#1269), so an
# image that needs a password from one exits before it gets an address. It must
# also declare no `VOLUME`, because removing the container leaves an anonymous
# volume behind (#1321).
_IMAGE_SOURCE = ("nginx", "1.27-alpine")
_IMAGE_REF = ":".join(_IMAGE_SOURCE)


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return (
        subprocess.run(["docker", "info"], capture_output=True, text=True).returncode
        == 0
    )


@pytest.mark.skipif(not _docker_available(), reason="docker daemon not available")
def test_realize_materializes_runtime_node_and_starts_image_node_together(tmp_path):
    free_container = "aptl-free-box"
    image_container = "aptl-image-box"

    _materialized_project(tmp_path)
    backend = DockerComposeBackend(project_dir=tmp_path, project_name="aptl-mixed-test")

    free_node = DeploymentNodeRealization(
        address="provision.node.free-box",
        name="free-box",
        service_name="free-box",
        container_name=free_container,
        networks=("mixed-net",),
        network_attachments=(
            DeploymentNetworkAttachment(
                network="mixed-net", ipv4_address="172.31.0.10"
            ),
        ),
        os="linux",
        os_version="",
        runtime=RuntimeConfiguration(
            packages=[RuntimePackage(manager="apt", name="curl", version="*")]
        ),
    )
    image_node = DeploymentNodeRealization(
        address="provision.node.image-box",
        name="image-box",
        service_name="image-box",
        container_name=image_container,
        networks=("mixed-net",),
        network_attachments=(
            DeploymentNetworkAttachment(
                network="mixed-net", ipv4_address="172.31.0.11"
            ),
        ),
        os="linux",
        os_version="",
        runtime=None,
    )
    spec = DeploymentRealizationSpec(
        profiles=("default",),
        nodes=(free_node, image_node),
        networks=(
            DeploymentNetworkRealization(
                name="mixed-net", cidr="172.31.0.0/24", gateway="172.31.0.1"
            ),
        ),
        images=(
            DeploymentImageRealization(
                address="provision.node.image-box",
                service_name="image-box",
                source_name=_IMAGE_SOURCE[0],
                source_version=_IMAGE_SOURCE[1],
                image_ref=_IMAGE_REF,
                mode="pull",
                policy_rule="allowed-source",
            ),
        ),
    )
    # Routing is per-node, not a whole-spec flag (the flag was removed): the
    # runtime-only node is materialized, the image node stays a Compose service,
    # and because a Compose node remains the mixed path runs.
    from aptl.core.deployment._compose_base_container_realization import (
        _base_container_node_addresses,
    )
    from aptl.core.deployment._compose_realization import _needs_compose

    materialized = _base_container_node_addresses(spec)
    assert free_node.address in materialized
    assert image_node.address not in materialized
    assert _needs_compose(spec) is True

    try:
        result = backend.realize(spec, build=False, scenario_root=tmp_path)
        assert result.success, result.error

        # Realized resources carry workspace-scoped names (#1054), so every
        # direct daemon read below has to name what actually exists.
        realized_free = realized_container_name(backend, free_container)
        realized_image = realized_container_name(backend, image_container)
        project = realized_project_name(backend)

        # Exactly one container for the runtime: node - Compose was told to
        # scale it to zero, so it never started its own "sleep infinity"
        # placeholder alongside the generic materializer's real container.
        ps = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name=^{realized_free}$",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
        )
        assert ps.stdout.split() == [realized_free]

        # The runtime: node was materialized directly (generic materializer),
        # not via Compose - it is not a Compose-managed container.
        assert (
            "curl"
            in backend.container_exec(
                realized_free, ["dpkg-query", "-W", "-f=${Package}\n", "curl"]
            ).stdout
        )

        # The source: node was started via Compose as usual and serves.
        served = None
        for _ in range(20):
            served = backend.container_exec(
                realized_image, ["wget", "-qO-", "http://127.0.0.1/"]
            )
            if served.returncode == 0:
                break
            time.sleep(1)
        assert served is not None
        assert served.returncode == 0, served.stdout
        assert "nginx" in served.stdout

        # The generic materializer's directly-run container is connected to
        # the declared scenario network with its declared static IP, exactly
        # like a Compose-managed node - the existing post-start network
        # reconciliation step operates by container name, so it already
        # covers both realization styles without any change.
        network = f"{project}_aptl-mixed"
        inspect = subprocess.run(
            [
                "docker",
                "inspect",
                realized_free,
                "--format",
                f'{{{{(index .NetworkSettings.Networks "{network}").IPAddress}}}}',
            ],
            capture_output=True,
            text=True,
        )
        assert inspect.stdout.strip() == "172.31.0.10", (inspect.stdout, inspect.stderr)
        networks = subprocess.run(
            [
                "docker",
                "inspect",
                realized_free,
                "--format",
                "{{json .NetworkSettings.Networks}}",
            ],
            capture_output=True,
            text=True,
        )
        assert '"bridge"' not in networks.stdout
    finally:
        # Removing the declared names removed nothing and leaked a container
        # and a network per run; the leaked subnet then failed the next run.
        project = realized_project_name(backend)
        subprocess.run(
            [
                "docker",
                "rm",
                "-f",
                realized_container_name(backend, free_container),
                realized_container_name(backend, image_container),
            ],
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "docker",
                "network",
                "rm",
                f"{project}_aptl-mixed",
                f"{project}_default",
            ],
            capture_output=True,
            text=True,
        )
