"""Construct the installed components of one admitted RAES runtime target."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from raes_runtime.registry import ReferenceTimeRuntime, RuntimeTarget

from aptl.backends._raes_runtime_target_options import RuntimeTargetOptions
from aptl.backends.raes_evaluator import AptlEvaluator
from aptl.backends.raes_manifest import APTL_RAES_TARGET_NAME, create_aptl_manifest
from aptl.backends.raes_observability_scope import ObservabilityScopeDecision
from aptl.backends.raes_operator_access import OperatorAccessDecision
from aptl.backends.raes_orchestrator import AptlOrchestrator
from aptl.backends.raes_participant_actions import DEFAULT_PARTICIPANT_ACTIONS
from aptl.backends.raes_participant_runtime import AptlParticipantRuntime
from aptl.backends.raes_planning_compat import resolve_target_planning_compatibility
from aptl.backends.raes_provisioner import AptlProvisioner
from aptl.core.config import AptlConfig
from aptl.core.experiment.capture_plan import empty_capture_plan
from aptl.core.scenario_bundle import ScenarioBundle

if TYPE_CHECKING:
    from aptl.core.deployment.backend import DeploymentBackend


def create_aptl_runtime_target(
    *,
    project_dir: Path,
    config: AptlConfig,
    backend: "DeploymentBackend",
    bundle: ScenarioBundle,
    options: RuntimeTargetOptions | None = None,
) -> RuntimeTarget:
    """Build APTL's canonical ``full-remote-control-plane`` runtime target.

    ``bundle`` is required: the target realizes exactly one scenario, and every
    scenario-declared input resolves against ``bundle.root``. Callers resolve it
    once at ingress with ``project_tree_bundle`` (issue #874).

    ``artifact_availability`` carries the trusted availability facts to the
    provisioner so realization starts each dynamic-composition node from the
    substrate config id availability verified, never a second tag resolution
    (issue #876 cycle-6 review).
    """

    selected = options or RuntimeTargetOptions()
    provisioner = AptlProvisioner(
        project_dir=project_dir,
        config=config,
        deployment_backend=backend,
        bundle=bundle,
        artifact_availability=selected.artifact_availability,
        capture_plan=selected.capture_plan or empty_capture_plan(),
        observability_scope=selected.observability_scope
        or ObservabilityScopeDecision(),
        operator_access=selected.operator_access or OperatorAccessDecision(),
        startup_selection=selected.startup_selection,
        planning_compatibility=resolve_target_planning_compatibility(bundle, config),
    )
    orchestrator = AptlOrchestrator()
    action_specs = dict(DEFAULT_PARTICIPANT_ACTIONS)
    if selected.participant_action_specs:
        action_specs.update(selected.participant_action_specs)
    participant_runtime = AptlParticipantRuntime(
        deployment_backend=backend,
        action_specs=action_specs,
        plan_authority=selected.participant_plan_authority,
        autonomous_bindings=selected.autonomous_bindings,
    )
    capture_registry = (
        selected.capture_selection.registry
        if selected.capture_selection is not None
        else None
    )
    return RuntimeTarget(
        name=APTL_RAES_TARGET_NAME,
        manifest=create_aptl_manifest(
            capture_registry,
            participant_inject_delivery=selected.participant_inject_delivery,
            autonomous_bindings=selected.autonomous_bindings,
        ),
        provisioner=provisioner,  # type: ignore[arg-type]
        orchestrator=orchestrator,  # type: ignore[arg-type]
        evaluator=AptlEvaluator(
            proposition_interpreter=(
                selected.capture_selection.contribution.proposition_interpreter
                if selected.capture_selection is not None
                else None
            )
        ),  # type: ignore[arg-type]
        participant_runtime=participant_runtime,  # type: ignore[arg-type]
        time_runtime=(
            ReferenceTimeRuntime()
            if selected.participant_inject_delivery or selected.autonomous_bindings
            else None
        ),
    )
