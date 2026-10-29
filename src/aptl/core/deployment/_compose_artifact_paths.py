"""Canonical host paths of the generated artifacts that Compose binds."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from aptl.core.credentials import RENDERED_MANAGER_RELPATH
from aptl.core.deployment._flag_signing_keys import FLAG_SIGNING_PROFILE_V2
from aptl.core.deployment._ssh_key_bundle import SSH_ACCESS_PROFILE_V1
from aptl.core.deployment._misp_cache_credential import (
    MISP_CACHE_CREDENTIAL_PROFILE,
)
from aptl.core.deployment._misp_fastcgi_loopback import (
    MISP_FASTCGI_LOOPBACK_PROFILE,
)
from aptl.core.deployment._misp_server_tls import MISP_SERVER_TLS_PROFILE
from aptl.core.deployment._cortex_service_credentials import (
    CORTEX_SERVICE_CREDENTIALS_PROFILE,
    CORTEX_SERVICE_CREDENTIALS_ROOT_RELPATH,
)
from aptl.core.deployment._compose_stateful_constants import (
    CERTIFICATE_ROOT_RELPATH,
    CERTIFICATE_PROVENANCE,
    FLAG_SIGNING_ROOT_RELPATH,
    MISP_CACHE_CREDENTIAL_ROOT_RELPATH,
    MISP_FASTCGI_LOOPBACK_ROOT_RELPATH,
    MISP_SERVER_TLS_ROOT_RELPATH,
    SOC_CERT_PROFILE,
    SOC_CERTS_ROOT_RELPATH,
    SSH_KEY_BUNDLE_ROOT_RELPATH,
    WAZUH_MANAGER_CONFIG_PROVENANCES,
    WAZUH_CERT_PROFILES,
)

if TYPE_CHECKING:
    from aptl.core.deployment.realization import (
        DeploymentGeneratedArtifactRealization,
    )


def artifact_source_path(
    scenario_root: Path,
    artifact: DeploymentGeneratedArtifactRealization,
) -> Path:
    """Return the canonical host source for a supported artifact provider.

    A generated artifact is scenario-local: it is produced and read back under
    the scenario bundle root, not the engine checkout. For an in-tree scenario
    the two coincide (issue #874).
    """

    provenance = getattr(artifact, "provenance", None)
    if provenance == SOC_CERT_PROFILE:
        relative = Path(SOC_CERTS_ROOT_RELPATH)
    elif artifact.generator == "certificate_bundle" and provenance in {CERTIFICATE_PROVENANCE, *WAZUH_CERT_PROFILES}:
        relative = Path(CERTIFICATE_ROOT_RELPATH)
    elif artifact.generator == "ssh_key_bundle" and provenance == SSH_ACCESS_PROFILE_V1:
        relative = Path(SSH_KEY_BUNDLE_ROOT_RELPATH) / artifact.name
    elif provenance == FLAG_SIGNING_PROFILE_V2:
        relative = Path(FLAG_SIGNING_ROOT_RELPATH) / artifact.name
    elif provenance == CORTEX_SERVICE_CREDENTIALS_PROFILE:
        relative = Path(CORTEX_SERVICE_CREDENTIALS_ROOT_RELPATH)
    elif provenance == MISP_CACHE_CREDENTIAL_PROFILE:
        relative = Path(MISP_CACHE_CREDENTIAL_ROOT_RELPATH)
    elif provenance == MISP_SERVER_TLS_PROFILE:
        relative = Path(MISP_SERVER_TLS_ROOT_RELPATH)
    elif provenance == MISP_FASTCGI_LOOPBACK_PROFILE:
        relative = Path(MISP_FASTCGI_LOOPBACK_ROOT_RELPATH)
    elif provenance in WAZUH_MANAGER_CONFIG_PROVENANCES:
        relative = Path(RENDERED_MANAGER_RELPATH)
    else:
        raise ValueError("unsupported generated artifact producer")
    return scenario_root.resolve() / relative


def artifact_environment_file_path(
    scenario_root: Path,
    artifact: DeploymentGeneratedArtifactRealization,
    service_name: str,
) -> Path:
    """Return a contained opaque path for one generated environment delivery."""

    artifact_key = hashlib.sha256(artifact.address.encode()).hexdigest()[:20]
    service_key = hashlib.sha256(service_name.encode()).hexdigest()[:20]
    return (
        scenario_root.resolve()
        / ".aptl/realization/generated-environment"
        / artifact_key
        / f"{service_key}.env"
    )
