"""Adjust compiled RAES realization requirements for one compatibility decision."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from raes_contracts.explicitness import ExplicitnessClass
from raes_contracts.planning import (
    RealizationAuthorityMode,
    RealizationResolutionSource,
)
from raes_contracts.vocabulary import ObservationStrength
from raes_processor.models import RuntimeModel

from aptl.backends import (
    _raes_backend_implementation_profiles as implementation_profiles,
)
from aptl.backends.scenario_planning_compatibility import (
    PlanningCompatibilityDecision,
)


def _requirement_identity(item: object) -> tuple[object, ...]:
    """Return the stable identity joining a requirement to its authority."""

    return (
        getattr(item, "address", None),
        getattr(item, "field_path", None),
        getattr(item, "domain", None),
        getattr(item, "requirement_kind", None),
    )


def _authored_paths(scenario: object | None) -> frozenset[str] | None:
    """Index exact and ancestor paths from the parser's authority map once."""

    explicitness = getattr(scenario, "explicitness", None)
    if not isinstance(explicitness, Mapping):
        return None
    paths: set[str] = set()
    for path in explicitness:
        paths.add(path)
        paths.update(path[:index] for index, char in enumerate(path) if char in ".[")
    return frozenset(paths)


def _authored_concern(paths: frozenset[str] | None, requirement: object) -> bool:
    """An explicit empty field counts; an absent parser default does not."""

    field_path = getattr(requirement, "field_path", None)
    return paths is None or not isinstance(field_path, str) or field_path in paths


def _selected_open_requirement(
    scenario: object | None,
    requirement: object,
    decision: PlanningCompatibilityDecision,
    authored_paths: frozenset[str] | None,
) -> bool:
    """Keep authored state and the two open defaults APTL actually selects."""

    kind = getattr(requirement, "requirement_kind", None)
    return (
        scenario is None
        or getattr(requirement, "explicitness", None) is not ExplicitnessClass.OPEN
        or _authored_concern(authored_paths, requirement)
        or _backend_profile_selects_concern(scenario, requirement)
        or (
            kind in decision.open_default_concerns
            and _image_backed_node(scenario, requirement)
        )
    )


def _backend_profile_selects_concern(scenario: object, requirement: object) -> bool:
    """Keep authority for mechanics selected by a semantic backend profile."""

    nodes = getattr(scenario, "nodes", None)
    address = getattr(requirement, "address", None)
    kind = getattr(requirement, "requirement_kind", None)
    if not isinstance(nodes, Mapping) or not isinstance(address, str):
        return False
    node = next(
        (item for name, item in nodes.items() if address == f"provision.node.{name}"),
        None,
    )
    runtime = getattr(node, "runtime", None) if node is not None else None
    return isinstance(
        kind, str
    ) and kind in implementation_profiles.backend_profile_selected_concerns(runtime)


def _image_backed_node(scenario: object, requirement: object) -> bool:
    """Return whether a requirement's node has a materialized image source."""

    nodes = getattr(scenario, "nodes", None)
    address = getattr(requirement, "address", None)
    if not isinstance(nodes, Mapping) or not isinstance(address, str):
        return True
    node = next(
        (item for name, item in nodes.items() if address == f"provision.node.{name}"),
        None,
    )
    return node is None or getattr(node, "source", None) is not None


def apply_planning_compatibility(
    model: RuntimeModel,
    decision: PlanningCompatibilityDecision | None,
    *,
    scenario: object | None = None,
) -> RuntimeModel:
    """Apply one adapter's validated bounded compatibility decision.

    Configuration-scope corroboration remains mandatory and no evidence is
    relabelled.  For the finite concern set whose released OPEN relation RAES
    cannot evaluate, APTL commits its least-intrusive choice: exactly the
    authored value, with no backend additions, verified by native readback.
    """

    if decision is None:
        return model

    authored_paths = _authored_paths(scenario)
    authority_identities = {
        _requirement_identity(item) for item in model.realization_authority
    }
    adjusted_identities: set[tuple[object, ...]] = set()
    delegated_identities: set[tuple[object, ...]] = set()
    exact_identities: set[tuple[object, ...]] = set()
    requirements = []
    for requirement in model.realization_requirements:
        requirement, adjusted, delegated, exact = _adjust_requirement(
            requirement,
            scenario=scenario,
            authored_paths=authored_paths,
            authority_identities=authority_identities,
            decision=decision,
        )
        identity = _requirement_identity(requirement)
        if adjusted:
            adjusted_identities.add(_requirement_identity(requirement))
        if delegated:
            delegated_identities.add(identity)
        if exact:
            exact_identities.add(identity)
        requirements.append(requirement)

    if not adjusted_identities and not delegated_identities and not exact_identities:
        return model

    authority = tuple(
        _adjust_authority(
            item,
            adjusted_identities,
            delegated_identities,
            exact_identities,
        )
        for item in model.realization_authority
    )
    return replace(
        model,
        realization_requirements=tuple(requirements),
        realization_authority=authority,
    )


def _adjust_requirement(
    requirement: object,
    *,
    scenario: object | None,
    authored_paths: frozenset[str] | None,
    authority_identities: set[tuple[object, ...]],
    decision: PlanningCompatibilityDecision,
) -> tuple[object, bool, bool, bool]:
    """Apply delegation and provenance compatibility to one requirement."""

    identity = _requirement_identity(requirement)
    delegated = identity in authority_identities and not _selected_open_requirement(
        scenario, requirement, decision, authored_paths
    )
    if delegated:
        requirement = replace(requirement, explicitness=None, delegated=True)
    exact = _requires_exact_native_evidence(requirement, authored_paths, decision)
    if exact:
        requirement = replace(
            requirement,
            explicitness=ExplicitnessClass.EXACT,
            structure=None,
            constraint_document=None,
            constraint_binding=None,
            recursive_pending=False,
        )
    adjusted = (
        not requirement.delegated
        and requirement.requirement_kind in decision.daemon_readback_concerns
        and requirement.required_observation_strength
        is ObservationStrength.GUEST_OBSERVED
    )
    if adjusted:
        requirement = replace(
            requirement,
            required_observation_strength=ObservationStrength.DAEMON_OBSERVED,
        )
    return requirement, adjusted, delegated, exact


def _requires_exact_native_evidence(
    requirement: object,
    authored_paths: frozenset[str] | None,
    decision: PlanningCompatibilityDecision,
) -> bool:
    """Return whether minimum intrusion closes an authored open concern."""

    authored = _authored_concern(authored_paths, requirement)
    return bool(
        not requirement.delegated
        and requirement.explicitness is ExplicitnessClass.OPEN
        and requirement.requirement_kind in decision.minimum_intrusion_exact_concerns
        and authored
    )


def _adjust_authority(
    authority: object,
    adjusted: set[tuple[object, ...]],
    delegated: set[tuple[object, ...]],
    exact: set[tuple[object, ...]],
) -> object:
    """Mirror an adjusted requirement onto its compiled authority."""

    identity = _requirement_identity(authority)
    if identity in delegated:
        return replace(
            authority,
            delegated=True,
            source=RealizationResolutionSource.APPARATUS_DEFAULT,
        )
    if identity in exact:
        authority = replace(authority, mode=RealizationAuthorityMode.EXACT)
    if (
        identity in adjusted
        and authority.required_observation_strength
        is ObservationStrength.GUEST_OBSERVED
    ):
        return replace(
            authority,
            required_observation_strength=ObservationStrength.DAEMON_OBSERVED,
        )
    return authority
