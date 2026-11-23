"""Capabilities of the installed native runtime readers."""

from collections.abc import Mapping

from raes_contracts.vocabulary import ObservationStrength

from aptl.backends._raes_runtime_container_observation import CONTAINER_DAEMON_FIELDS


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
        },
        ObservationStrength.DAEMON_OBSERVED,
    ),
    **dict.fromkeys(
        {
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
    """Admit explicit evidence-source declarations from installed code."""

    from raes_processor.semantics.realization import CONCERN_PAYLOAD_PATH

    sources = getattr(provider, "observed_runtime_concerns", {})
    if not isinstance(sources, Mapping) or len(sources) > 128:
        raise ValueError("runtime-reader-declaration-invalid")
    if sources and not callable(getattr(provider, "observe_runtime", None)):
        raise ValueError("runtime-reader-declaration-invalid")
    return {
        kind: _admitted_concern_source(kind, source, CONCERN_PAYLOAD_PATH)
        for kind, source in sources.items()
    }


_DECLARABLE_SOURCES = frozenset(
    {
        ObservationStrength.DRIVER_REPORTED,
        ObservationStrength.DAEMON_OBSERVED,
        ObservationStrength.GUEST_OBSERVED,
    }
)


def _admitted_concern_source(
    kind: object, source: object, known_kinds: Mapping[str, object]
) -> ObservationStrength:
    """Admit one declared concern source unless it conflicts with the core source."""
    if kind not in known_kinds or source not in _DECLARABLE_SOURCES:
        raise ValueError("runtime-reader-declaration-invalid")
    selected = ObservationStrength(source)
    core = CORE_RUNTIME_CONCERN_SOURCES.get(kind)
    # Installed image adapters may declare their baked software inventory.
    baked_inventory = (
        kind == "runtime-software-components"
        and selected is ObservationStrength.DRIVER_REPORTED
    )
    if core is not None and selected != core and not baked_inventory:
        raise ValueError("runtime-reader-source-conflict")
    return selected
