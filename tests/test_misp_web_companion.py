"""Issue #1407: MISP 2.5.50 serves HTTPS through a pinned web companion.

From misp-docker v2.5.46, ``misp-core`` runs php-fpm only and the web tier
ships as ``misp-nginx``. Every MISP image with PHP fixed for CVE-2026-109618
and CVE-2026-109619 has that split, so the backend realizes the pack's one
``misp`` node as the core image plus a web companion that joins its network
namespace. The node keeps one network identity and its declared 443 listener.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_NGINX_IMAGE = (
    "ghcr.io/misp/misp-docker/misp-nginx@sha256:"
    "10d8a3af27f49ade99e8f4a8f75802f5d5c565eb38635ac110da9dfb84534c7e"
)


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
