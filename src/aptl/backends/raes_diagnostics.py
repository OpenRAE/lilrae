"""Diagnostics and runtime-state helpers for the APTL RAES backend."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from copy import deepcopy

from raes_contracts.apparatus import RealizationVerificationScope
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.planning import (
    ChangeAction,
    ProvisioningPlan,
    RealizationAuthorityMode,
    RuntimeDomain,
)
from raes_contracts.runtime_state import (
    RealizationObservationDisclosure,
    RuntimeSnapshot,
    SnapshotEntry,
)
from raes_contracts.vocabulary import ObservationStrength
from raes_processor.semantics.realization import CONCERN_PAYLOAD_PATH
from raes_runtime.backend_account_credentials import plan_has_account_credentials

from aptl.backends.raes_observation import ObservedResource
from aptl.backends.raes_planning_compat import DAEMON_READBACK_RUNTIME_CONCERNS
from aptl.utils.logging import get_logger
from aptl.utils.redaction import redact

log = get_logger("raes-diagnostics")

PROVISIONING_ADDRESS = "runtime.apply.provisioning"
DEFAULT_STAGE_LABEL = "RAES runtime handoff failed"
SUPPORTED_RESOURCE_TYPES = frozenset(
    {
        "network",
        "node",
        "feature-binding",
        "content-placement",
        "account-placement",
        "domain-controller-placement",
        "generated-artifact",
        "persistent-volume",
    }
)

_GUEST_READBACK_RUNTIME_CONCERNS = frozenset(
    {
        "process-resource-limits",
        "runtime-dependency-manifests",
        "runtime-filesystem-inventory",
        "runtime-local-identity",
        "runtime-packages",
        "runtime-service-manager-units",
    }
)
_RUNTIME_READBACK_CONCERNS = (
    DAEMON_READBACK_RUNTIME_CONCERNS
    | _GUEST_READBACK_RUNTIME_CONCERNS
    | {"forwarding-agents"}
)
_APPLIED_ENTRY_STATUS = "applied"
_UNCHANGED_ENTRY_STATUS = "unchanged"


def diagnostic(code: str, address: str, message: str) -> Diagnostic:
    """Build a redacted RAES error diagnostic."""
    return Diagnostic(
        code=code,
        domain=RuntimeDomain.PROVISIONING.value,
        address=address,
        message=redact(message),
        severity=Severity.ERROR,
    )


def has_error(diagnostics: list[Diagnostic]) -> bool:
    """Return whether any diagnostic is error severity."""
    return any(item.is_error for item in diagnostics)


_RENDERED_DIAGNOSTIC_CAP = 5


def render_raes_diagnostics(
    diagnostics: list[Diagnostic], *, stage_label: str = DEFAULT_STAGE_LABEL
) -> str:
    """Render RAES diagnostics into the APTL ``LabResult`` error surface.

    ``stage_label`` names the failing phase and defaults to the original
    hard-coded ``"RAES runtime handoff failed"`` prefix, so every existing
    caller is unchanged. ADR-047's error envelope reuses this same
    formatter for the experiment-admission failure surface by passing a
    distinct label (e.g. ``"RAES experiment admission failed"``) instead of
    adding a second formatter — do not misclassify admission as a
    startup-readiness warning by leaving the default label in place there.

    The error surface stays bounded, but truncation must never be silent: a
    dropped diagnostic can be the actionable one (issue #677), so the full
    rendered set always lands in the log and the surface names how many
    entries it omitted.
    """
    if not diagnostics:
        return f"{stage_label}."
    rendered = [_format_diagnostic(item) for item in diagnostics if item.is_error]
    if not rendered:
        rendered = [_format_diagnostic(item) for item in diagnostics]
    shown = rendered[:_RENDERED_DIAGNOSTIC_CAP]
    if len(rendered) > _RENDERED_DIAGNOSTIC_CAP:
        for item in rendered:
            log.error("RAES diagnostic: %s", redact(item))
        shown = [
            *shown,
            f"[{len(rendered) - _RENDERED_DIAGNOSTIC_CAP} more diagnostics "
            "omitted; full set in the log]",
        ]
    return redact(f"{stage_label}: " + "; ".join(shown))


def unsupported_resource_diagnostics(
    plan: ProvisioningPlan,
) -> list[Diagnostic]:
    """Return diagnostics for RAES resources APTL cannot realize."""
    diagnostics: list[Diagnostic] = []
    seen: set[tuple[str, str]] = set()
    for resource in [*plan.resources.values(), *plan.operations]:
        resource_type = resource.resource_type
        key = (resource.address, resource_type)
        if resource_type in SUPPORTED_RESOURCE_TYPES or key in seen:
            continue
        seen.add(key)
        diagnostics.append(
            diagnostic(
                "aptl.provisioner.unsupported-resource-type",
                resource.address,
                (
                    "APTL provisioning target does not support RAES "
                    f"resource type '{resource_type}'."
                ),
            )
        )
    return diagnostics


def snapshot_after_apply(
    plan: ProvisioningPlan,
    snapshot: RuntimeSnapshot,
    observations: Mapping[str, ObservedResource],
) -> RuntimeSnapshot:
    """Return a snapshot of what the backend was observed to have realized.

    Each entry's payload carries the concern values the backend actually
    realized (:mod:`aptl.backends.raes_observation`), not the planned ones. A
    resource the backend did not realize gets no entry: the SEM-218 gate treats
    an absent EXACT concern as a silent approximation and rejects it, which is
    the point — echoing the plan back made the gate compare the plan against
    itself and pass unconditionally (issue #578).

    Each entry's status names what the backend did with its operation. For a
    plan with account credentials, RAES's closed result contract also requires
    every value outside an admitted concern to equal the plan's, and admits no
    backend evidence in an entry (ADR-046).
    """
    entries = dict(snapshot.entries)
    actions = {op.address: op.action for op in plan.operations}
    for op in plan.operations:
        if op.action == ChangeAction.DELETE:
            entries.pop(op.address, None)
    admitted = _admitted_concern_kinds(plan)
    evidence = not plan_has_account_credentials(plan)
    for address, resource in plan.resources.items():
        observed = observations.get(address)
        if observed is None or not observed.realized:
            entries.pop(address, None)
            continue
        entries[address] = SnapshotEntry(
            address=address,
            domain=RuntimeDomain.PROVISIONING,
            resource_type=resource.resource_type,
            payload=_observed_payload(
                resource.payload,
                observed,
                resource.resource_type,
                None if admitted is None else admitted.get(address, frozenset()),
                evidence=evidence,
            ),
            ordering_dependencies=resource.ordering_dependencies,
            refresh_dependencies=resource.refresh_dependencies,
            status=_entry_status(actions.get(address)),
        )
    observations_disclosure = _realization_observation_disclosures(observations)
    updated = snapshot.with_entries(entries)
    if observations_disclosure:
        updated = dataclasses.replace(
            updated,
            realization_observations=(
                *updated.realization_observations,
                *observations_disclosure,
            ),
        )
    return updated


def _realization_observation_disclosures(
    observations: Mapping[str, ObservedResource],
) -> tuple[RealizationObservationDisclosure, ...]:
    """Disclose how APTL corroborated each realized ``configuration``-scope concern.

    RAES's runtime gate accepts a concern with a non-null
    verification scope only when the returned snapshot carries a matching
    observation disclosure whose scope and strength the backend manifest also
    declares. Disclose only a concern present in the actual observation map;
    absence therefore still fails closed instead of turning a capability claim
    into evidence.
    """

    disclosures: list[RealizationObservationDisclosure] = []
    for address, observed in observations.items():
        node_name = address.removeprefix("provision.node.")
        for kinds, strength in (
            (
                DAEMON_READBACK_RUNTIME_CONCERNS | {"forwarding-agents"},
                ObservationStrength.DAEMON_OBSERVED,
            ),
            (_GUEST_READBACK_RUNTIME_CONCERNS, ObservationStrength.GUEST_OBSERVED),
        ):
            for kind in sorted(kinds):
                path = CONCERN_PAYLOAD_PATH[kind]
                if path not in observed.concerns:
                    continue
                disclosures.append(
                    RealizationObservationDisclosure(
                        address=address,
                        field_path=f"nodes.{node_name}." + ".".join(path[2:]),
                        domain="runtime-realization",
                        requirement_kind=kind,
                        verification_scope=RealizationVerificationScope.CONFIGURATION,
                        observation_strength=strength,
                    )
                )
    return tuple(disclosures)


def _entry_status(action: ChangeAction | None) -> str:
    """Name what the backend did with one planned operation."""

    if action is ChangeAction.UNCHANGED:
        return _UNCHANGED_ENTRY_STATUS
    return _APPLIED_ENTRY_STATUS


def _admitted_concern_kinds(
    plan: ProvisioningPlan,
) -> dict[str, frozenset[str]] | None:
    """Return, per address, the concern kinds whose realized value RAES reads.

    Only a plan with account credentials needs this: RAES requires every
    returned value outside these concerns to equal the plan's. They are the
    plan's open, constrained and exact authorities and its planned constraints
    (RAES plans constraints only for ``compute-substrate`` today, which APTL
    does not write; a wider one must never echo the plan). A closed concern, or
    one with no authority at an address, is plan-owned: RAES accepts it absent
    or equal to the plan and reads no observation from it. RAES also reads
    compiled requirements that are not in the plan; its authority completeness
    check gives every registry concern that applies to an operation a plan
    authority, so they admit no concern outside these. ``None`` keeps every
    unobserved concern removed, for any other plan and for a plan without
    realization authority, whose admission comes from a compiled model the
    backend never sees.
    """

    if not (plan.realization_authority and plan_has_account_credentials(plan)):
        return None
    admitted: dict[str, set[str]] = {}
    for authority in plan.realization_authority:
        if authority.mode is not RealizationAuthorityMode.CLOSED:
            kinds = admitted.setdefault(authority.address, set())
            kinds.add(authority.requirement_kind)
    for constraint in plan.realization_constraints:
        admitted.setdefault(constraint.address, set()).add(constraint.concern)
    return {address: frozenset(kinds) for address, kinds in admitted.items()}


def realized_changed_addresses(
    plan: ProvisioningPlan,
    snapshot: RuntimeSnapshot,
) -> list[str]:
    """Return changed addresses that the resulting snapshot actually carries.

    RAES rejects a backend that reports a changed address outside its snapshot
    transition, and an unrealized resource now has no entry — so a planned
    change the backend did not realize must not be claimed as changed.
    """

    return [
        op.address
        for op in plan.operations
        if op.action != ChangeAction.UNCHANGED and op.address in snapshot.entries
    ]


def _observed_payload(
    planned_payload: Mapping[str, object],
    observed: ObservedResource,
    resource_type: str,
    admitted_kinds: frozenset[str] | None,
    *,
    evidence: bool,
) -> dict[str, object]:
    """Return the planned payload with realization concerns replaced by reality.

    Non-concern fields (names, specs, addresses) are descriptive identity the
    backend does not realize a value for, so they are carried through. The
    concern fields the gate compares are overwritten with what was observed, and
    an admitted concern the backend could not be seen to realize is removed
    entirely rather than left echoing the plan. An unobserved concern outside
    ``admitted_kinds`` is plan-owned like a name and keeps the plan's value;
    ``None`` admits every concern. Source-image evidence is added only when
    ``evidence`` is set; otherwise the run outcome alone carries it.
    """

    payload = deepcopy(dict(planned_payload))
    concern_kinds = {
        "node": (
            "node-type",
            "os-family",
            "domain-topology",
            # raes 3.1.0 per-node runtime realization concerns (#876): observed
            # off the realized container and written at their nested payload
            # paths, or removed so an unrealized EXACT declaration is rejected.
            *sorted(_RUNTIME_READBACK_CONCERNS),
        ),
        # ADR-088 (#889): a content-placement carrying a service materialization
        # exposes the service-search-index-schema-materialization concern, which
        # the gate replaces with the corroborated observation (or removes when
        # unproven, so planned state is never accepted).
        "content-placement": (
            "content-type",
            "service-search-index-schema-materialization",
        ),
        "generated-artifact": ("generated-artifact",),
        "persistent-volume": ("persistent-volume",),
    }.get(resource_type, ())
    for kind in concern_kinds:
        path = CONCERN_PAYLOAD_PATH[kind]
        if path in observed.concerns:
            _set_path(payload, path, observed.concerns[path])
        elif admitted_kinds is None or kind in admitted_kinds:
            _pop_path(payload, path)
    source_image = observed.evidence.get("source_image")
    if evidence and isinstance(source_image, dict):
        payload["backend_evidence"] = {"source_image": deepcopy(source_image)}
    return payload


def _set_path(payload: dict[str, object], path: tuple[str, ...], value: object) -> None:
    """Set a nested concern value, building intermediate mappings as needed."""

    current = payload
    for key in path[:-1]:
        nested = current.get(key)
        if not isinstance(nested, dict):
            nested = {}
            current[key] = nested
        current = nested
    current[path[-1]] = value


def _pop_path(payload: dict[str, object], path: tuple[str, ...]) -> None:
    """Remove a nested concern value, leaving other payload fields intact."""

    current: object = payload
    for key in path[:-1]:
        if not isinstance(current, dict) or key not in current:
            return
        current = current[key]
    if isinstance(current, dict):
        current.pop(path[-1], None)


def _format_diagnostic(item: Diagnostic) -> str:
    """Format one diagnostic line for operator-facing output."""
    return f"{item.code} at {item.address}: {item.message}"
