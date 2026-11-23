"""Read-only runtime qualification for Compose deployment backends."""

from __future__ import annotations

from pathlib import Path

from aptl.core.deployment._compose_node_generation import (
    render_realization_compose,
)
from aptl.core.deployment.realization import DeploymentRealizationSpec
from aptl.core.deployment.runtime_materialization import (
    SHARED_DOCKER_PROFILE,
    RuntimeMaterializationIssue,
    RuntimeMaterializationProfile,
    effective_runtime_contract_issues,
    qualify_runtime_materialization,
)
from aptl.core.lab_types import LabResult


def _issues_failure(
    issues: tuple[RuntimeMaterializationIssue, ...],
) -> LabResult | None:
    """Project bounded qualification issues into a deployment result."""

    return (
        LabResult(
            success=False,
            error="; ".join(issue.render() for issue in issues[:5]),
        )
        if issues
        else None
    )


class ComposeRuntimeMaterializationMixin:
    """Qualify runtime authority before ownership or Docker mutation."""

    def qualify_runtime_materialization(
        self,
        realization: DeploymentRealizationSpec,
        *,
        scenario_root: Path,
    ) -> LabResult:
        """Expose the read-only graph gate to pre-build scenario admission.

        The backend protocol supplies a scenario root; this pure qualification
        uses only the typed graph, without reading scenario files.
        """

        del scenario_root
        failure = self._runtime_materialization_preflight(realization)
        return failure or LabResult(success=True)

    @staticmethod
    def _runtime_materialization_profile(
        realization: DeploymentRealizationSpec,
    ) -> RuntimeMaterializationProfile:
        """Return the backend envelope proven before deployment mutation."""

        del realization
        return SHARED_DOCKER_PROFILE

    def _runtime_materialization_preflight(
        self,
        realization: DeploymentRealizationSpec,
    ) -> LabResult | None:
        """Qualify the complete runtime graph without creating backend state."""

        profile = self._runtime_materialization_profile(realization)
        issues = qualify_runtime_materialization(
            realization,
            profile=profile,
        )
        failure = _issues_failure(issues)
        if failure is None:
            failure = self._rendered_runtime_contract_failure(realization, profile)
        return failure

    @staticmethod
    def _rendered_runtime_contract_failure(
        realization: DeploymentRealizationSpec,
        profile: RuntimeMaterializationProfile,
    ) -> LabResult | None:
        """Exercise pure image-backed lowering before mixed dispatch."""

        try:
            rendered = render_realization_compose(realization)
        except ValueError as exc:
            return LabResult(
                success=False,
                error=(
                    "aptl.provisioner.runtime-materialization-unsupported: "
                    f"backend={profile.name} limitation={exc}"
                ),
            )
        issues = effective_runtime_contract_issues(
            rendered,
            realization,
            profile=profile,
        )
        return _issues_failure(issues)
