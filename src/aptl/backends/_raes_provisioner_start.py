"""Starting a lowered deployment and reporting what it actually realized.

Two halves of one apply: start the deployment and verify every added observer,
then read the realized world back until its native evidence settles. The
readback loop exists because application-owned inventories settle after
Compose's health gate — a bounded retry, never an admission that an absent or
partial value is good enough.

Split out of ``raes_provisioner`` so the plan-validation half and the
start-and-observe half each stay inside a file a reader can hold in their head.
"""

from __future__ import annotations

import time
from dataclasses import replace

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel
from raes_contracts.realization_observation import RealizationObservationDisclosure
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.planner import realization_authority_disclosure

from aptl.backends._raes_apply_reporting import (
    bounded_apply_details as _bounded_apply_details,
    capture_apparatus_observations,
)
from aptl.backends._lilrae_catalog_image_observation import catalog_images_unverified
from aptl.backends._raes_image_policy import _policy_diagnostic
from aptl.backends._raes_observation_helpers import ObservedResource
from aptl.backends._raes_provisioning_helpers import (
    retryable_readback_gaps as _retryable_readback_gaps,
)
from aptl.backends.raes_diagnostics import (
    PROVISIONING_ADDRESS,
    diagnostic,
    realized_changed_addresses,
    snapshot_after_apply,
    unobserved_admitted_concerns,
)
from aptl.backends.raes_manifest import (
    create_aptl_manifest,
    create_aptl_realization_envelope,
)
from aptl.backends.raes_observation import (
    observation_evidence,
    observe_realization,
    operational_realization_observations,
)
from aptl.backends.raes_realization import AptlRealization
from aptl.core.deployment._operator_access_proof import operator_access_details
from aptl.core.deployment.observation import DeploymentObservationContext
from aptl.core.deployment.realization import DeploymentRealizationSpec
from aptl.core.execution_boundary import (
    BoundaryProbeBackend,
    disclosed_execution_boundary,
    has_bound_daemon_identity,
    revalidate_execution_boundary,
)
from aptl.utils.logging import get_logger

log = get_logger("raes-provisioner")

# Application-owned inventories can settle after Compose's health gate. Retry
# bounded native readback without admitting an absent or partial value.
_REALIZATION_READBACK_TIMEOUT_SECONDS = 300.0
_REALIZATION_READBACK_INTERVAL_SECONDS = 2.0


def execution_boundary_disclosure(
    backend: BoundaryProbeBackend,
    *,
    host_system: str | None = None,
    host_kernel: str | None = None,
) -> dict[str, object]:
    """Publish per-run facts in RAES's validated backend-owned apply details."""

    observed = disclosed_execution_boundary(backend)
    if observed is None:
        observed = revalidate_execution_boundary(
            backend, host_system=host_system, host_kernel=host_kernel
        )
    return observed.model_dump(mode="json")


def _required_seat_identity_unavailable(
    backend: BoundaryProbeBackend, *, bound_identity: bool, containment: str
) -> bool:
    """A required seat must have a readable daemon and containment label."""

    required_seat = isinstance(getattr(backend, "_appliance_boundary", None), tuple)
    return required_seat and (not bound_identity or containment == "unknown")


def _boundary_admission_failed(backend: BoundaryProbeBackend) -> bool:
    """Reject changed daemons and required seats with unreadable identities."""

    observed = revalidate_execution_boundary(backend)
    bound_identity = has_bound_daemon_identity(backend)
    changed_bound_daemon = observed.observation_status == "mismatch" and bound_identity
    return changed_bound_daemon or _required_seat_identity_unavailable(
        backend, bound_identity=bound_identity, containment=observed.host_containment
    )


def _boundary_failure_diagnostics(backend: BoundaryProbeBackend) -> list[Diagnostic]:
    """Return the boundary mismatch diagnostic when admission no longer holds."""

    if not _boundary_admission_failed(backend):
        return []
    return [
        diagnostic(
            "aptl.provisioner.execution-boundary-mismatch",
            PROVISIONING_ADDRESS,
            "Selected Docker endpoint or daemon changed or required seat identity is unavailable.",
        )
    ]


def _unsettled_readback(
    plan: ProvisioningPlan,
    snapshot: RuntimeSnapshot,
    readback_diagnostics: list[Diagnostic],
) -> tuple[bool, tuple[tuple[str, str], ...]]:
    """Return whether readback may still settle, and the concerns it missed.

    RAES names every gap its authority check finds. Only when it finds none can
    a missed admitted concern reach RAES's credential check, whose refusal names
    nothing, so readback waits for that concern too.
    """

    if readback_diagnostics:
        return _retryable_readback_gaps(plan, snapshot, readback_diagnostics), ()
    unobserved = unobserved_admitted_concerns(plan, snapshot)
    return bool(unobserved), unobserved


def _unobserved_concern_diagnostic(address: str, kind: str) -> Diagnostic:
    """Name one admitted concern that readback never observed."""

    return diagnostic(
        "aptl.provisioner.admitted-concern-unobserved",
        address,
        f"Realization readback did not observe the admitted '{kind}' concern "
        "before its deadline; a credential-bearing result must report it.",
    )


class ProvisionerStartMixin(object):
    """Start the lowered deployment, then report the world it realized."""

    def _realize_backend(
        self,
        deployment_spec: DeploymentRealizationSpec,
        observation_context: DeploymentObservationContext,
    ) -> str | None:
        """Start the backend and return an actionable failure reason, if any."""

        try:
            start_result = self.deployment_backend.realize(
                deployment_spec,
                scenario_root=self.bundle.root,
                substrate_digests=self._availability_substrate_digests(),
                observation_context=observation_context,
            )
        # The RAES backend-call boundary replaces a TypeError or ValueError
        # escaping apply() with an opaque contract diagnostic. Deployment
        # lowering uses those exception types for invalid realized service
        # models, so preserve the actionable, redacted reason here.
        except (TypeError, ValueError) as exc:
            return str(exc)
        if not start_result.success:
            return start_result.error or "APTL deployment backend failed."
        return None

    def _start_and_observe_apparatus(
        self,
        deployment_spec: DeploymentRealizationSpec,
        snapshot: RuntimeSnapshot,
        diagnostics: list[Diagnostic],
        selected_profiles: list[str],
        realization: AptlRealization,
    ) -> (
        tuple[DeploymentObservationContext, tuple[dict[str, object], ...]] | ApplyResult
    ):
        """Start the lowered deployment and verify every added observer."""

        observation_context = DeploymentObservationContext(attempt_id=self._attempt_id)
        result: ApplyResult | None = None
        boundary_failures = _boundary_failure_diagnostics(self.deployment_backend)
        if boundary_failures:
            diagnostics.extend(boundary_failures)
            return self._failed_apply(
                snapshot, diagnostics, selected_profiles, realization
            )
        start_error = self._realize_backend(deployment_spec, observation_context)
        if start_error is not None:
            diagnostics.append(
                diagnostic(
                    "aptl.provisioner.backend-start-failed",
                    PROVISIONING_ADDRESS,
                    start_error,
                )
            )
            result = self._failed_apply(
                snapshot, diagnostics, selected_profiles, realization
            )
        apparatus_observations = (
            capture_apparatus_observations(self.deployment_backend, deployment_spec)
            if result is None
            else None
        )
        if result is None and apparatus_observations is None:
            diagnostics.append(
                diagnostic(
                    "aptl.capture-apparatus.realization-unverified",
                    PROVISIONING_ADDRESS,
                    "Required capture apparatus could not be verified after realization.",
                )
            )
            result = self._failed_apply(
                snapshot, diagnostics, selected_profiles, realization
            )
        return result or (observation_context, apparatus_observations or ())

    def _successful_apply(
        self,
        plan: ProvisioningPlan,
        snapshot: RuntimeSnapshot,
        diagnostics: list[Diagnostic],
        realization: AptlRealization,
        observation_context: DeploymentObservationContext,
        apparatus_observations: tuple[dict[str, object], ...],
    ) -> ApplyResult:
        """Observe and report one deployment whose start checks succeeded."""

        selected_profiles = self.selected_profiles(realization)
        realization_envelope = create_aptl_realization_envelope()
        deadline = time.monotonic() + _REALIZATION_READBACK_TIMEOUT_SECONDS
        attempts = 0
        while True:
            attempts += 1
            # The snapshot must record what the backend realized, not what the
            # plan asked for: the SEM-218 gate reads the realized value out of
            # it, so echoing the plan back would make the gate compare the plan
            # against itself and pass unconditionally (issue #578).
            observations = observe_realization(
                self.deployment_backend,
                realization,
                plan,
                scenario_root=self.bundle.root,
                observation_context=observation_context,
                startup_selection=self.startup_selection,
            )
            unverified_images = catalog_images_unverified(observations)
            if unverified_images:
                diagnostics.extend(
                    _policy_diagnostic(address, "catalog-image-unverified")
                    for address in unverified_images
                )
                return _unverified_catalog_image_result(
                    snapshot, diagnostics, selected_profiles, realization, observations
                )
            realized_snapshot, operational_observations = self._realized_snapshot(
                plan,
                snapshot,
                observations,
                realization,
                observation_context,
                realization_envelope,
            )
            validation_snapshot = replace(
                realized_snapshot,
                realization_observations=(
                    *realized_snapshot.realization_observations,
                    *operational_observations,
                ),
            )
            readback_diagnostics, _ = realization_authority_disclosure(
                plan,
                validation_snapshot,
                manifest=create_aptl_manifest(),
            )
            settling, unobserved = _unsettled_readback(
                plan, validation_snapshot, readback_diagnostics
            )
            if not settling:
                break
            unsettled = len(readback_diagnostics) or len(unobserved)
            now = time.monotonic()
            if now >= deadline:
                log.warning(
                    "Realization readback deadline expired with %d unsettled native evidence records",
                    unsettled,
                )
                break
            if attempts == 1:
                log.info(
                    "Waiting for %d native realization evidence records to settle",
                    unsettled,
                )
            time.sleep(min(_REALIZATION_READBACK_INTERVAL_SECONDS, deadline - now))
        failures = [
            *(_unobserved_concern_diagnostic(*gap) for gap in unobserved),
            *_boundary_failure_diagnostics(self.deployment_backend),
        ]
        if failures:
            diagnostics.extend(failures)
            return self._failed_apply(
                snapshot, diagnostics, selected_profiles, realization
            )
        result = ApplyResult(
            success=True,
            snapshot=realized_snapshot,
            diagnostics=diagnostics,
            changed_addresses=realized_changed_addresses(plan, realized_snapshot),
            details=self._successful_apply_details(
                realization, observations, apparatus_observations
            ),
            operational_realization_observations=operational_observations,
        )
        from aptl.backends.lilrae_apparatus_reporting import append_verified_apparatus

        return append_verified_apparatus(
            result, self._lilrae_apparatus_resources, apparatus_observations
        )

    def _realized_snapshot(
        self,
        plan: ProvisioningPlan,
        snapshot: RuntimeSnapshot,
        observations: dict[str, ObservedResource],
        realization: AptlRealization,
        observation_context: DeploymentObservationContext,
        realization_envelope: BackendRealizationEnvelopeModel,
    ) -> tuple[RuntimeSnapshot, tuple[RealizationObservationDisclosure, ...]]:
        """Build the realized snapshot and its operational observations."""

        realized_snapshot = self._with_artifact_satisfactions(
            plan,
            snapshot_after_apply(plan, snapshot, observations),
            realization,
            observation_context,
        )
        realized_snapshot = replace(
            realized_snapshot,
            realization_envelope=realization_envelope.identity,
        )
        operational_observations = operational_realization_observations(
            plan=plan,
            observations=observations,
            envelope=realization_envelope,
            previous=realized_snapshot.realization_observations,
        )
        return realized_snapshot, operational_observations

    def _successful_apply_details(
        self,
        realization: AptlRealization,
        observations: dict[str, ObservedResource],
        apparatus_observations: tuple[dict[str, object], ...],
    ) -> dict[str, object]:
        """Project verified deployment and apparatus evidence into bounded details."""

        return _bounded_apply_details(
            {
                "profiles": self.selected_profiles(realization),
                "realization": realization.details(),
                "observation_evidence": observation_evidence(observations),
                "observability": {
                    "enabled": self.observability_scope.enabled,
                    "reason": self.observability_scope.reason,
                    "governing_scopes": list(self.observability_scope.governing_scopes),
                },
                "capture_apparatus": list(apparatus_observations),
                "operator_access": operator_access_details(self.operator_access.accesses),
                "aptl_execution_boundary": execution_boundary_disclosure(
                    self.deployment_backend
                ),
            },
            realization,
        )


def _unverified_catalog_image_result(
    snapshot: RuntimeSnapshot,
    diagnostics: list[Diagnostic],
    selected_profiles: list[str],
    realization: AptlRealization,
    observations: dict[str, ObservedResource],
) -> ApplyResult:
    """Return the failed apply for catalog images that APTL cannot verify."""

    return ApplyResult(
        success=False,
        snapshot=snapshot,
        diagnostics=diagnostics,
        details=_bounded_apply_details(
            {
                "profiles": selected_profiles,
                "realization": realization.details(),
                "observation_evidence": observation_evidence(observations),
            },
            realization,
        ),
    )
