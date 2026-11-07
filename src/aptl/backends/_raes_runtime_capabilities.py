"""Capabilities of the installed native runtime readers."""

from collections.abc import Mapping

from raes_contracts.vocabulary import ObservationStrength

from aptl.backends._raes_runtime_container_observation import CONTAINER_DAEMON_FIELDS
from aptl.backends.initial_service_inventory import RUNTIME_SERVICE_READERS


CORE_RUNTIME_CONCERN_SOURCES = {
    **dict.fromkeys(
        {
            *CONTAINER_DAEMON_FIELDS.values(),
            "linux-capabilities",
            "published-ports",
            "runtime-container-autoremove",
            "runtime-container-command",
            "runtime-container-entrypoint",
            "runtime-environment",
            "runtime-local-control-interfaces",
            "runtime-mounts",
            "runtime-node-memory-limit",
            "runtime-restart-policy",
            "service-listeners",
            "runtime-orchestration-authorities",
        },
        ObservationStrength.DAEMON_OBSERVED,
    ),
    **dict.fromkeys(
        {
            *(RUNTIME_SERVICE_READERS.keys() - {"runtime-orchestration-authorities"}),
            "forwarding-agents",
            "process-resource-limits",
            "runtime-dependency-manifests",
            "runtime-filesystem-inventory",
            "runtime-local-identity",
            "runtime-packages",
            "runtime-service-manager-units",
            "runtime-software-components",
        },
        ObservationStrength.GUEST_OBSERVED,
    ),
}


def adapter_runtime_concern_sources(
    provider: object | None,
) -> dict[str, ObservationStrength]:
    """Admit only explicit independent-readback declarations from installed code."""

    from raes_processor.semantics.realization import CONCERN_PAYLOAD_PATH

    sources = getattr(provider, "observed_runtime_concerns", {})
    if not isinstance(sources, Mapping) or len(sources) > 128:
        raise ValueError("runtime-reader-declaration-invalid")
    if sources and not callable(getattr(provider, "observe_runtime", None)):
        raise ValueError("runtime-reader-declaration-invalid")
    result = {}
    for kind, source in sources.items():
        if kind not in CONCERN_PAYLOAD_PATH or source not in {
            ObservationStrength.DAEMON_OBSERVED,
            ObservationStrength.GUEST_OBSERVED,
        }:
            raise ValueError("runtime-reader-declaration-invalid")
        selected = ObservationStrength(source)
        if (
            kind in CORE_RUNTIME_CONCERN_SOURCES
            and selected != CORE_RUNTIME_CONCERN_SOURCES[kind]
        ):
            raise ValueError("runtime-reader-source-conflict")
        result[kind] = selected
    return result
