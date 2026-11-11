"""Confine the pinned MISP core image's FastCGI listener to loopback.

From misp-docker v2.5.46, ``misp-core`` runs php-fpm only and its entrypoint
always sets ``PHP_LISTEN_FPM=true``, which rewrites the ``www`` pool to listen
on ``[::]:9002``. Unauthenticated FastCGI runs arbitrary PHP, so that listener
must not be reachable from the node's networks. The web companion joins the
node's network namespace and is the only client, so loopback is enough.

php-fpm includes ``pool.d/*.conf`` in order and lets a later file re-open the
``www`` pool. This module stages one such file, and the realization mounts it
read-only beside the image's own ``www.conf``. It is a delivery shape for a
backend choice, not scenario content: nothing here derives from the pack.
"""

from __future__ import annotations

from pathlib import Path

from aptl.core.credentials import (
    _atomic_write_secure,
    _canonical_generated_path,
    _ensure_secure_dir,
)
from aptl.core.deployment._compose_stateful_constants import (
    MISP_FASTCGI_LOOPBACK_ROOT_RELPATH,
)
from aptl.core.deployment.realization import DeploymentGeneratedArtifactRealization

MISP_FASTCGI_LOOPBACK_PROFILE = "lilrae:misp-fastcgi-loopback/v1"

#: The pinned image's php-fpm pool include directory.
MISP_FASTCGI_LOOPBACK_MOUNT_DESTINATION = "/etc/php/8.4/fpm/pool.d"
MISP_FASTCGI_LOOPBACK_OUTPUT = "pool-override"
#: Sorts after the image's ``www.conf``, so its values win.
MISP_FASTCGI_LOOPBACK_FILENAME = "zz-lilrae-loopback.conf"

#: The web companion reaches FastCGI here inside the shared network namespace.
MISP_FASTCGI_LOOPBACK_LISTEN = "127.0.0.1:9002"
#: php-fpm status stays disabled; the web image still needs a resolvable target.
MISP_FASTCGI_STATUS_LISTEN = "127.0.0.1:9003"

MISP_FASTCGI_LOOPBACK_CONTENT = (
    "; Written by LilRAE. FastCGI runs arbitrary PHP, so only the MISP web\n"
    "; companion in this network namespace may reach it.\n"
    "[www]\n"
    f"listen = {MISP_FASTCGI_LOOPBACK_LISTEN}\n"
)


def realize_misp_fastcgi_loopback(
    artifact: DeploymentGeneratedArtifactRealization,
    scenario_root: Path,
) -> str | None:
    """Stage the php-fpm pool override that binds FastCGI to loopback."""

    actual = {output.name: output.path for output in artifact.outputs}
    if (
        artifact.provenance != MISP_FASTCGI_LOOPBACK_PROFILE
        or artifact.lifecycle != "reuse_valid"
        or actual != {MISP_FASTCGI_LOOPBACK_OUTPUT: MISP_FASTCGI_LOOPBACK_FILENAME}
    ):
        return "MISP FastCGI loopback artifact does not match its producer contract."
    try:
        root = _canonical_generated_path(
            scenario_root, MISP_FASTCGI_LOOPBACK_ROOT_RELPATH
        )
        _ensure_secure_dir(root)
        target = _canonical_generated_path(
            scenario_root,
            MISP_FASTCGI_LOOPBACK_ROOT_RELPATH / MISP_FASTCGI_LOOPBACK_FILENAME,
        )
        _atomic_write_secure(target, MISP_FASTCGI_LOOPBACK_CONTENT)
    except (OSError, ValueError):
        return "MISP FastCGI loopback staging failed."
    return None


__all__ = (
    "MISP_FASTCGI_LOOPBACK_CONTENT",
    "MISP_FASTCGI_LOOPBACK_FILENAME",
    "MISP_FASTCGI_LOOPBACK_LISTEN",
    "MISP_FASTCGI_LOOPBACK_MOUNT_DESTINATION",
    "MISP_FASTCGI_LOOPBACK_OUTPUT",
    "MISP_FASTCGI_LOOPBACK_PROFILE",
    "MISP_FASTCGI_STATUS_LISTEN",
    "realize_misp_fastcgi_loopback",
)
