"""Backend implementation choice for the Wazuh Dashboard (#1422)."""

from __future__ import annotations

from aptl.backends._raes_backend_implementation_types import (
    BackendImplementationProfile,
    SemanticRuntimeSelector,
    environment as _environment,
    published_port as _port,
    variable as _variable,
)
from aptl.core.deployment._compose_content_mounts import (
    OWNED_CONTENT_IMAGE_USER_INSTALLER,
)

_BIN_SH = "/bin/sh"
_DASHBOARD_HOME = "/usr/share/wazuh-dashboard"
_DASHBOARD_KEYSTORE = f"{_DASHBOARD_HOME}/bin/opensearch-dashboards-keystore"
#: The pinned image's `/entrypoint.sh` steps, with the owned-content install
#: placed after its app-config step. That step appends a default `hosts` key to
#: a writable `wazuh.yml` that lacks the image's own host id, which makes the
#: declared file invalid YAML, so declared content must write it last. The image
#: entrypoint ignores the app-config status, and so does this one. Unlike the
#: image, it has no default indexer login: an unset login stops the start.
DASHBOARD_START = (
    ': "${DASHBOARD_USERNAME:?}" "${DASHBOARD_PASSWORD:?}"; '
    "/wazuh_app_config.sh || true; "
    f"{OWNED_CONTENT_IMAGE_USER_INSTALLER}; "
    f"yes | {_DASHBOARD_KEYSTORE} create --allow-root; "
    'printf "%s\\n" "$DASHBOARD_USERNAME" | '
    f"{_DASHBOARD_KEYSTORE} add opensearch.username --stdin --allow-root; "
    'printf "%s\\n" "$DASHBOARD_PASSWORD" | '
    f"{_DASHBOARD_KEYSTORE} add opensearch.password --stdin --allow-root; "
    f"exec {_DASHBOARD_HOME}/bin/opensearch-dashboards "
    f"-c {_DASHBOARD_HOME}/config/opensearch_dashboards.yml"
)

WAZUH_DASHBOARD_PROFILE = BackendImplementationProfile(
    profile_id="wazuh-dashboard-4.12",
    selector=SemanticRuntimeSelector(
        "platform_applications", "product", "Wazuh Dashboard", "4.12.0"
    ),
    source_name="wazuh/wazuh-dashboard",
    source_version="4.12.0",
    image_ref=(
        "wazuh/wazuh-dashboard@sha256:"
        "8f5b50fde67a0b1c4d2321aa26b12bbc5cef21269cf4f6225746f0b946458bd7"
    ),
    runtime_selections={
        # The image runs as `wazuh-dashboard`, and the pack authors its
        # configs as `wazuh-dashboard`-owned 0600 files. A bind mount keeps
        # the host owner, so the image user installs them itself (#1422).
        "runtime-container-entrypoint": [_BIN_SH, "-ec", DASHBOARD_START],
        "runtime-environment": _environment(
            _variable(
                "INDEXER_USERNAME",
                classification="secret_fixture",
                provenance="runtime",
            ),
            _variable(
                "INDEXER_PASSWORD",
                classification="secret_fixture",
                provenance="runtime",
            ),
            _variable(
                "DASHBOARD_USERNAME",
                classification="secret_fixture",
                provenance="runtime",
            ),
            _variable(
                "DASHBOARD_PASSWORD",
                classification="secret_fixture",
                provenance="runtime",
            ),
            _variable(
                "API_USERNAME",
                classification="secret_fixture",
                provenance="runtime",
            ),
            _variable(
                "API_PASSWORD",
                classification="secret_fixture",
                provenance="runtime",
            ),
            _variable("WAZUH_API_URL", "https://wazuh.manager"),
        ),
        "published-ports": [_port(5601, 443)],
    },
)
