"""The released TechVault AD node carries only its provider capability (#1700)."""

from __future__ import annotations

import pytest

from aptl.backends.raes_node_materialization import realize_node
from aptl.core.deployment.docker_compose import DockerComposeBackend
from tests.test_compose_capability_necessity import _PRIVILEGE_FLAGS, _StartRecorder


@pytest.fixture(scope="module")
def rendered_techvault(released_techvault_realization):
    """The pinned TechVault pack, realized once per test session without Docker."""
    return released_techvault_realization


def test_the_realized_ad_node_carries_only_the_provider_capability(
    rendered_techvault, tmp_path
):
    """`ad` in Compose is a scale-to-zero stub; the grant lives on the provider.

    So the check drives the pinned pack's realized `ad` node through the
    materializer to the base container it starts, and renders that
    container's `docker run` command (#954). The Samba provider adds
    SYS_ADMIN and nothing else, the scenario authors no capability of its
    own, and no security option or namespace flag comes with it.
    """

    ad = next(node for node in rendered_techvault.nodes if node.name == "ad")
    backend = _StartRecorder()

    result = realize_node(ad, backend)

    assert len(backend.started) == 1, result
    assert not backend.copied, result
    (started,) = backend.started
    argv = DockerComposeBackend(tmp_path)._base_container_create_command(
        started, None, started.image_ref
    )
    # Docker reads both `--cap-add X` and `--cap-add=X`.
    added = [argv[index + 1] for index, flag in enumerate(argv) if flag == "--cap-add"]
    added += [flag.split("=", 1)[1] for flag in argv if flag.startswith("--cap-add=")]
    assert ad.runtime is None or ad.runtime.linux_capabilities is None
    assert added == ["SYS_ADMIN"]
    assert not {flag.split("=", 1)[0] for flag in argv} & _PRIVILEGE_FLAGS, argv
