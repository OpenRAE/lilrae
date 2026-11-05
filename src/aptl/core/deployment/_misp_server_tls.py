"""Deliver the pack's MISP leaf certificate where its image actually reads it.

The released TechVault pack owns this material: ``techvault-soc-certificates``
declares ``misp-certificate`` and ``misp-private-key``, and mounts them into the
MISP node at ``/opt/techvault/soc-certs``. That destination is the scenario's
substrate-neutral statement of *what* MISP receives. It is not where the
selected component looks: from misp-docker v2.5.46 the web tier is the
pinned ``misp-nginx`` companion, which reads ``/etc/nginx/certs/cert.pem`` and
``/etc/nginx/certs/key.pem`` (issue #1407). Choosing how an authored
certificate reaches the selected image is a backend concern, so APTL makes that
choice here.

A consumer mount lowers to ``mount_destination / output.path`` for both its
host source and its container target, so the host file has to carry the
image-native name. This module therefore stages a copy of the pack-produced
leaf under image-native filenames. The SOC certificate bundle remains the sole
*producer* of the material -- nothing here mints a key, derives an identity, or
signs anything. It is a delivery shape, and it is refreshed whenever the
bundle's bytes change so a rotated certificate can never leave a stale copy
serving traffic.
"""

from __future__ import annotations

from pathlib import Path

from aptl.core.credentials import (
    _FILE_MODE,
    _atomic_write_secure,
    _canonical_generated_path,
    _enforce_mode,
    _ensure_secure_dir,
)
from aptl.core.deployment._compose_stateful_constants import (
    MISP_SERVER_TLS_ROOT_RELPATH,
    SOC_CERTS_ROOT_RELPATH,
)
from aptl.core.deployment.realization import DeploymentGeneratedArtifactRealization

MISP_SERVER_TLS_PROFILE = "techvault:misp-server-tls/v1"

#: Where the pinned web companion's nginx configuration reads its TLS material.
MISP_SERVER_TLS_MOUNT_DESTINATION = "/etc/nginx/certs"
#: The MISP companion role that terminates TLS for the node's 443 listener.
MISP_WEB_COMPANION_ROLE = "web"
MISP_SERVER_TLS_CERTIFICATE_OUTPUT = "server-certificate"
MISP_SERVER_TLS_PRIVATE_KEY_OUTPUT = "server-private-key"

#: Output name -> (image-native relative path, path within the SOC bundle).
_EXPECTED_OUTPUTS = {
    MISP_SERVER_TLS_CERTIFICATE_OUTPUT: ("cert.pem", "misp/server.pem"),
    MISP_SERVER_TLS_PRIVATE_KEY_OUTPUT: ("key.pem", "misp/server.key"),
}


def realize_misp_server_tls(
    artifact: DeploymentGeneratedArtifactRealization,
    scenario_root: Path,
) -> str | None:
    """Stage the pack's MISP leaf under the filenames its image reads."""

    actual = {output.name: output.path for output in artifact.outputs}
    expected = {name: relative for name, (relative, _) in _EXPECTED_OUTPUTS.items()}
    invalid_contract = (
        artifact.provenance != MISP_SERVER_TLS_PROFILE
        or artifact.lifecycle != "reuse_valid"
        or actual != expected
    )
    error = (
        "MISP server TLS artifact does not match its producer contract."
        if invalid_contract
        else stage_misp_server_tls(scenario_root)
    )
    return error


def stage_misp_server_tls(scenario_root: Path) -> str | None:
    """Copy the SOC bundle's MISP leaf into the web companion's native layout.

    Realization calls this through its generated artifact. The in-tree start
    calls it directly, because the root Compose file mounts the same copy.
    """

    try:
        root = _canonical_generated_path(scenario_root, MISP_SERVER_TLS_ROOT_RELPATH)
        _ensure_secure_dir(root)
        for relative, source_relative in _EXPECTED_OUTPUTS.values():
            source = _canonical_generated_path(
                scenario_root, SOC_CERTS_ROOT_RELPATH / source_relative
            )
            content = source.read_text(encoding="utf-8")
            if not content.strip():
                return (
                    "MISP server TLS material is missing from the certificate bundle."
                )
            target = _canonical_generated_path(
                scenario_root, MISP_SERVER_TLS_ROOT_RELPATH / relative
            )
            # 0644 under the owner-only staging root, as for every rendered
            # credential: the web companion's nginx runs as uid 101, so an
            # owner-only key would be unreadable across the bind mount. An
            # unchanged copy from an earlier start may still be owner-only.
            if _current(target) == content:
                _enforce_mode(target, _FILE_MODE, "file")
            else:
                _atomic_write_secure(target, content)
    except (OSError, ValueError):
        return "MISP server TLS staging failed."
    return None


def _current(path: Path) -> str | None:
    """Return the staged bytes, or ``None`` when nothing is staged yet."""

    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


__all__ = (
    "MISP_SERVER_TLS_CERTIFICATE_OUTPUT",
    "MISP_SERVER_TLS_MOUNT_DESTINATION",
    "MISP_SERVER_TLS_PRIVATE_KEY_OUTPUT",
    "MISP_SERVER_TLS_PROFILE",
    "MISP_WEB_COMPANION_ROLE",
    "realize_misp_server_tls",
    "stage_misp_server_tls",
)
