"""Disclose service configuration once, after deployment's initial readback."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aptl.backends.raes_realization_model import AptlRealization
    from aptl.backends._raes_observation_helpers import ObservedResource
    from aptl.core.deployment.backend import DeploymentBackend

from raes_processor.semantics.realization import CONCERN_PAYLOAD_PATH

from aptl.backends._runtime_concern_disclosure import _record
from aptl.backends.database_inventory import observe_database_services
from aptl.backends.datastore_inventory import observe_datastores
from aptl.backends.application_inventory import (
    observe_applications,
    observe_platform_applications,
)
from aptl.backends.detection_inventory import observe_sensors, observe_detection_engines
from aptl.backends.monitoring_inventory import observe_monitoring_managers
from aptl.backends.orchestration_inventory import observe_orchestration_authorities
from aptl.backends.service_inventory import (
    observe_dns_services,
    observe_file_services,
    observe_identity_authorities,
)


RUNTIME_SERVICE_READERS = {
    "runtime-applications": observe_applications,
    "runtime-platform-applications": observe_platform_applications,
    "runtime-network-sensors": observe_sensors,
    "runtime-network-detection-engines": observe_detection_engines,
    "runtime-security-monitoring-managers": observe_monitoring_managers,
    "runtime-orchestration-authorities": observe_orchestration_authorities,
    "runtime-identity-authorities": lambda b, n, ns: observe_identity_authorities(
        b, n.container_name, n.runtime
    ),
    "runtime-file-services": lambda b, n, ns: observe_file_services(
        b, n.container_name, n.runtime
    ),
    "runtime-dns-services": lambda b, n, ns: observe_dns_services(
        b, n.container_name, n.runtime
    ),
    "runtime-database-services": lambda b, n, ns: observe_database_services(
        b, n.container_name, n.runtime
    ),
    "runtime-datastore-services": observe_datastores,
}


def observe_initial_services(
    backend: DeploymentBackend,
    realization: AptlRealization,
    observations: dict[str, ObservedResource],
) -> None:
    """Add only successful native observations to the existing initial report."""
    for node in realization.nodes:
        observed = observations.get(node.address)
        if (
            node.runtime is None
            or node.container_name is None
            or observed is None
            or not observed.realized
        ):
            continue
        for kind, reader in RUNTIME_SERVICE_READERS.items():
            _record(
                observed.concerns,
                CONCERN_PAYLOAD_PATH[kind],
                lambda reader=reader: reader(backend, node, realization.nodes),
            )
