"""The TechVault adapter's native runtime concern readers."""

from __future__ import annotations

from collections.abc import Callable

from raes_contracts.vocabulary import ObservationStrength
from raes_processor.semantics.realization import CONCERN_PAYLOAD_PATH

from aptl.backends.scenario_runtime_hooks import disclose_runtime_concern
from aptl.core.runtime_readback import ConcernReading
from aptl_techvault.application_readback import (
    applications,
    app_authorizations,
    platform_applications,
)
from aptl_techvault.database_readback import database_services, datastore_services
from aptl_techvault.readback_support import ReadbackBackend
from aptl_techvault.security_readback import (
    network_detection_engines,
    network_sensors,
    orchestration_authorities,
    security_monitoring_managers,
)
from aptl_techvault.service_readback import (
    dns_services,
    file_services,
    identity_authorities,
)
from aptl_techvault.software_readback import software_components

READERS: dict[str, Callable[[ReadbackBackend, object], list[dict[str, object]]]] = {
    "runtime-app-authorizations": app_authorizations,
    "runtime-applications": applications,
    "runtime-database-services": database_services,
    "runtime-datastore-services": datastore_services,
    "runtime-dns-services": dns_services,
    "runtime-file-services": file_services,
    "runtime-identity-authorities": identity_authorities,
    "runtime-network-detection-engines": network_detection_engines,
    "runtime-network-sensors": network_sensors,
    "runtime-orchestration-authorities": orchestration_authorities,
    "runtime-platform-applications": platform_applications,
    "runtime-security-monitoring-managers": security_monitoring_managers,
    "runtime-software-components": software_components,
}
OBSERVED_RUNTIME_CONCERNS = {
    kind: ObservationStrength.DAEMON_OBSERVED
    if kind == "runtime-orchestration-authorities"
    else ObservationStrength.GUEST_OBSERVED
    for kind in READERS
}


def observe_runtime(
    backend: ReadbackBackend, node: object
) -> dict[tuple[str, ...], ConcernReading]:
    """Withhold an unproven concern; no release or projection digest grants proof."""

    result = {}
    runtime = getattr(node, "runtime", None)
    if runtime is None or not getattr(node, "container_name", None):
        return result
    for kind, reader in READERS.items():
        path = CONCERN_PAYLOAD_PATH[kind]
        if not getattr(runtime, path[-1], None):
            continue
        try:
            native = reader(backend, node)
            if not native:
                continue
            disclosed = disclose_runtime_concern(kind, native)
            if disclosed is not None:
                result[path] = ConcernReading(
                    kind, disclosed, OBSERVED_RUNTIME_CONCERNS[kind]
                )
        except (
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            StopIteration,
            OSError,
        ):
            # No native output or exception detail enters the evidence or diagnostic surface.
            continue
    return result
