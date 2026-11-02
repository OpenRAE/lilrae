"""Realization and independent readback capabilities published by APTL."""

from raes_contracts.apparatus import (
    RealizationObservationCapability,
    RealizationSupportDeclaration,
    RealizationSupportMode,
    RealizationVerificationScope,
)
from raes_contracts.vocabulary import ObservationStrength

from aptl.backends._raes_manifest_resources import APTL_PROCESS_RESOURCE_LIMITS
from aptl.backends.raes_artifact_mechanisms import aptl_artifact_mechanisms
from dataclasses import replace
from collections.abc import Mapping

from aptl.backends._raes_runtime_capabilities import CORE_RUNTIME_CONCERN_SOURCES

DAEMON_READBACK_RUNTIME_CONCERNS = frozenset(
    kind for kind, source in CORE_RUNTIME_CONCERN_SOURCES.items()
    if source is ObservationStrength.DAEMON_OBSERVED
)


# What APTL realizes from a provisioning plan, and how. APTL matches declared
# capabilities against its provisioner support and discloses the result through
# the backend-manifest / operation-status / runtime-snapshot contracts. The
# constrained-kind set is intentionally narrower than the provisioner vocabulary.
# Parameterized OS, package and local identity declarations resolve before
# materialization and use the same independent readback as literal declarations.
# Node/content exact requirements use ``declared-capability-match``.
#
# ``artifact_mechanisms`` declares which RAES artifact-satisfaction routes APTL
# can admit (ADR-050, RAES ADR-098). It is deliberately narrow: a mechanism is
# advertised only once APTL can both materialize it and read the result back
# (SEM-218 I4). ``support_mode`` is OPEN_REALIZATION because APTL now supports the
# generic ``dynamic-composition`` route (issue #876): it composes a node's runtime
# onto a pinned substrate and reads every declared runtime concern back off the
# realized container (raes 3.1.0 lowers those concerns, OpenRAE/rae#985). The
# mode is the most-open posture for the domain; the exact and constrained branches
# still apply independently through the per-kind support sets below.
#
# ``source-artifact`` appears on the mechanism's ``supported_requirement_kinds``
# and on ``supported_constraint_kinds``, but deliberately NOT on
# ``supported_exact_requirement_kinds``. The two SEM-218 branches differ: the
# exact branch keys on the single ``declared-capability-match`` kind regardless
# of the requirement's own kind, so listing it there would claim a capability the
# gate never consults, while the constrained branch keys on the requirement's own
# kind and so genuinely needs it. The constrained claim is backed by the
# per-component build mechanism and its read-after-write of the built image.
APTL_REALIZATION_SUPPORT = (
    RealizationSupportDeclaration(
        domain="runtime-realization",
        support_mode=RealizationSupportMode.OPEN_REALIZATION,
        supported_constraint_kinds=frozenset(
            {
                "os-family",
                "source-artifact",
                "runtime-packages",
                "runtime-local-identity",
            }
        ),
        # ``service-search-index-schema-materialization`` (ADR-088, #889) is an
        # exact requirement kind APTL genuinely realizes through the native ES
        # materializer and reads back through the service's native interface, so
        # it is declared on the exact branch alongside the existing
        # node/content declared-capability-match kind.
        supported_exact_requirement_kinds=frozenset({
            *CORE_RUNTIME_CONCERN_SOURCES,
            "declared-capability-match",
            "service-search-index-schema-materialization",
        }),
        disclosure_kinds=frozenset(
            {"backend-manifest-v2", "operation-status-v1", "runtime-snapshot-v1"}
        ),
        # Per-concern observation capability. APTL corroborates environment,
        # mounts, capabilities, ports, listeners, and forwarding-agent state
        # from host-side native readback; package, filesystem, service-manager,
        # and operating-system identity require bounded guest readback. The
        # runtime discloses only facts actually observed, never a planned echo.
        observation_capabilities={
            **{
                kind: RealizationObservationCapability(
                    verification_scope=RealizationVerificationScope.CONFIGURATION,
                    observation_strength=source,
                )
                for kind, source in CORE_RUNTIME_CONCERN_SOURCES.items()
            },
            "operating-system": RealizationObservationCapability(
                verification_scope=RealizationVerificationScope.PRESENCE,
                observation_strength=ObservationStrength.GUEST_OBSERVED,
            ),
        },
        process_resource_limits=APTL_PROCESS_RESOURCE_LIMITS,
        artifact_mechanisms=list(aptl_artifact_mechanisms()),
        constraints={},
    ),
)


def realization_support_with_readers(
    sources: Mapping[str, ObservationStrength],
) -> tuple[RealizationSupportDeclaration, ...]:
    """Project admitted adapter readers without changing compiler authority."""

    declaration = APTL_REALIZATION_SUPPORT[0]
    capabilities = {
        **declaration.observation_capabilities,
        **{
            kind: RealizationObservationCapability(
                verification_scope=RealizationVerificationScope.CONFIGURATION,
                observation_strength=source,
            )
            for kind, source in sources.items()
        },
    }
    return (replace(
        declaration,
        supported_exact_requirement_kinds=declaration.supported_exact_requirement_kinds | sources.keys(),
        observation_capabilities=capabilities,
    ),)
