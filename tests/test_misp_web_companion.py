"""Issue #1407: MISP 2.5.50 serves HTTPS through a pinned web companion.

From misp-docker v2.5.46, ``misp-core`` runs php-fpm only and the web tier
ships as ``misp-nginx``. Every MISP image with PHP fixed for CVE-2026-109618
and CVE-2026-109619 has that split, so the backend realizes the pack's one
``misp`` node as the core image plus a web companion that joins its network
namespace. The node keeps one network identity and its declared 443 listener.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aptl.core.deployment._compose_node_generation import render_realization_compose
from aptl.core.deployment._misp_fastcgi_loopback import (
    MISP_FASTCGI_LOOPBACK_MOUNT_DESTINATION,
    realize_misp_fastcgi_loopback,
)
from aptl.core.deployment._misp_server_tls import MISP_SERVER_TLS_MOUNT_DESTINATION
from tests.techvault_pack import realize_techvault_pack

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_NGINX_IMAGE = (
    "ghcr.io/misp/misp-docker/misp-nginx@sha256:"
    "10d8a3af27f49ade99e8f4a8f75802f5d5c565eb38635ac110da9dfb84534c7e"
)


@pytest.fixture(scope="module")
def realization(tmp_path_factory):
    return realize_techvault_pack(tmp_path_factory.mktemp("misp-web-companion"))


@pytest.fixture(scope="module")
def services(realization):
    spec = realization.deployment_spec(sorted(realization.profiles))
    return render_realization_compose(spec)["services"]


def _misp(realization):
    return next(node for node in realization.nodes if node.name == "misp")


def test_misp_selects_one_pinned_web_companion(realization):
    (companion,) = _misp(realization).backend_companions

    assert companion.role == "web"
    assert companion.image.service_name == "misp-web"
    assert companion.image.image_ref == _NGINX_IMAGE
    assert companion.image.source_version == "2.5.50"
    assert companion.image.provenance_refs[0] == (
        "docker://ghcr.io/misp/misp-docker/misp-nginx:v2.5.50"
    )
    environment = dict(companion.environment)
    assert environment["NGINX_INTERNAL_HTTPS_PORT"] == "443"
    assert environment["FASTCGI_LISTEN"] == "127.0.0.1:9002"
    # The image defaults this upstream to ``misp-core:9003``, a name that does
    # not resolve here; nginx then refuses to start.
    assert environment["FASTCGI_LISTEN_STATUS"] == "127.0.0.1:9003"
    # The canonical URL is the node's authored setting, not a backend default.
    assert environment["BASE_URL"] == "https://misp.techvault.local"


def test_the_companion_joins_misp_without_added_authority(services):
    web = services["misp-web"]

    assert web["image"] == _NGINX_IMAGE
    assert web["container_name"] == "aptl-misp-web"
    assert web["network_mode"] == "service:misp"
    assert web["profiles"] == services["misp"]["profiles"]
    assert web["read_only"] is True
    assert web["cap_drop"] == ["ALL"]
    assert web["security_opt"] == ["no-new-privileges:true"]
    assert sorted(web["tmpfs"]) == [
        "/etc/nginx/conf.d:mode=0755,uid=101,gid=101",
        "/tmp:mode=1777",
        "/var/cache/nginx:mode=0755,uid=101,gid=101",
    ]
    assert web["labels"] == {
        "aptl.companion.of": "provision.node.misp",
        "aptl.companion.role": "web",
    }
    for field in ("hostname", "networks", "ports", "user", "privileged", "cap_add"):
        assert field not in web


def test_the_tls_leaf_is_delivered_to_the_web_companion(realization):
    artifact = next(
        item for item in realization.generated_artifacts if item.name == "misp-server-tls"
    )
    (consumer,) = artifact.consumers

    assert consumer.node_name == "misp"
    assert consumer.service_name == "misp-web"
    assert consumer.mount_destination == MISP_SERVER_TLS_MOUNT_DESTINATION


def test_fastcgi_is_confined_to_loopback(realization, tmp_path):
    """misp-core listens for FastCGI on every interface unless overridden.

    Unauthenticated FastCGI runs arbitrary PHP, so only the web companion in
    the same network namespace may reach it.
    """

    artifact = next(
        item
        for item in realization.generated_artifacts
        if item.name == "misp-fastcgi-loopback"
    )
    (consumer,) = artifact.consumers
    assert consumer.node_name == "misp"
    assert consumer.service_name == "misp"
    assert consumer.mount_destination == MISP_FASTCGI_LOOPBACK_MOUNT_DESTINATION
    assert consumer.access_mode == "read_only"

    assert realize_misp_fastcgi_loopback(artifact, tmp_path) is None

    (output,) = artifact.outputs
    staged = tmp_path / ".aptl/realization/misp-fastcgi-loopback" / output.path
    lines = [
        line
        for line in staged.read_text(encoding="utf-8").splitlines()
        if not line.startswith(";")
    ]
    assert lines == ["[www]", "listen = 127.0.0.1:9002"]
    assert staged.stat().st_mode & 0o777 == 0o644


def test_static_compose_runs_the_same_misp_web_tier(realization):
    """The root Compose file and the catalog cannot drift apart."""

    compose = yaml.safe_load((PROJECT_ROOT / "docker-compose.yml").read_text())
    misp = compose["services"]["misp"]
    web = compose["services"]["misp-web"]
    (companion,) = _misp(realization).backend_companions

    assert web["image"] == companion.image.image_ref
    assert web["network_mode"] == "service:misp"
    assert "FASTCGI_LISTEN_STATUS=127.0.0.1:9003" in web["environment"]
    assert web["read_only"] is True
    assert web["cap_drop"] == ["ALL"]
    assert web["security_opt"] == ["no-new-privileges:true"]
    assert {mount.split(":")[1] for mount in web["volumes"]} == {
        "/etc/nginx/certs/cert.pem",
        "/etc/nginx/certs/key.pem",
    }
    assert not any("/etc/nginx" in mount for mount in misp["volumes"])
    assert any(
        mount.split(":")[1].startswith(MISP_FASTCGI_LOOPBACK_MOUNT_DESTINATION + "/")
        for mount in misp["volumes"]
    )
    assert "nginx" not in " ".join(misp["healthcheck"]["test"])


def test_phased_starts_and_image_pulls_include_the_companion(realization):
    from aptl.core.deployment.realization import (
        companion_images,
        with_companion_services,
    )

    spec = realization.deployment_spec(sorted(realization.profiles))

    assert with_companion_services(spec, ("misp",)) == ("misp", "misp-web")
    assert with_companion_services(spec, ("misp-db",)) == ("misp-db",)
    assert [image.image_ref for image in companion_images(spec)] == [_NGINX_IMAGE]


def test_the_owner_is_not_healthy_until_its_companion_is(realization, mocker, tmp_path):
    from aptl.core.deployment import _compose_post_start
    from aptl.core.deployment.docker_compose import DockerComposeBackend

    wait = mocker.patch.object(
        _compose_post_start, "wait_for_realized_health", return_value=[]
    )
    spec = realization.deployment_spec(sorted(realization.profiles))

    DockerComposeBackend(tmp_path)._await_realized_service_health(spec)

    ongoing = wait.call_args.args[1]
    assert "aptl-misp" in ongoing
    assert "aptl-misp-web" in ongoing


def test_an_offline_seat_stages_the_companion_image(realization):
    from aptl.appliance.input_images import _scenario_image_references

    assert _scenario_image_references(realization)["scenario.misp-web"] == _NGINX_IMAGE


def test_the_root_compose_pool_override_is_the_rendered_one():
    from aptl.core.deployment._misp_fastcgi_loopback import (
        MISP_FASTCGI_LOOPBACK_CONTENT,
        MISP_FASTCGI_LOOPBACK_FILENAME,
    )

    tracked = PROJECT_ROOT / "config/misp" / MISP_FASTCGI_LOOPBACK_FILENAME

    assert tracked.read_text(encoding="utf-8") == MISP_FASTCGI_LOOPBACK_CONTENT


def test_an_authored_environment_keeps_tls_and_fastcgi_confinement():
    """Confinement belongs to the profile, not to environment defaulting (#1407)."""
    from types import SimpleNamespace

    from aptl.backends._raes_backend_generated_artifacts import (
        selected_generated_artifacts,
    )

    artifacts = selected_generated_artifacts(
        profile_id="misp-2.5.50",
        resource=SimpleNamespace(address="provision.node.misp"),
        service_name="misp",
        additions={},
        runtime=SimpleNamespace(environment=()),
    )

    assert {artifact.name for artifact in artifacts} == {
        "misp-server-tls",
        "misp-fastcgi-loopback",
    }
