"""Legacy fixed-probe execution behind the canonical participant runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from raes_contracts.contracts import ParticipantActionResultModel
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.participant_native_execution import ParticipantNativeActionExecution
from raes_contracts.participant_episode import ParticipantEpisodeExecutionState
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from aptl.backends.raes_participant_actions import (
    ParticipantActionSpec,
    drive_participant_action,
)

if TYPE_CHECKING:
    from aptl.core.deployment.backend import DeploymentBackend


def model_legacy_action(
    deployment_backend: DeploymentBackend,
    action_specs: Mapping[str, ParticipantActionSpec],
    request: ParticipantActionAdmissionRequest,
    snapshot: RuntimeSnapshot,
    *,
    episode_id: str,
) -> ParticipantNativeActionExecution:
    """Retain the old fixed probe only as an explicitly admitted smoke action."""

    state = ParticipantEpisodeExecutionState.from_payload(
        snapshot.participant_episode_results[request.participant_address]
    )
    execution = drive_participant_action(
        deployment_backend,
        action_specs,
        request.participant_address,
        state,
        timestamp_factory=lambda: state.updated_at,
    )
    if execution is None:
        return ParticipantNativeActionExecution(
            apply_result=ApplyResult(success=True, snapshot=snapshot),
            action_result=request.action_result,
            post_state_digest=request.post_state_digest,
        )
    observation_details = execution.behavior_events[-1].get("details", {})
    observations = [
        value
        for key in ("stdout_excerpt", "stderr_excerpt")
        if isinstance(observation_details, Mapping)
        and isinstance((value := observation_details.get(key)), str)
        and value
    ]
    result = ParticipantActionResultModel(
        status="succeeded" if execution.success else "failed",
        participant_address=request.participant_address,
        episode_id=episode_id,
        action_instance_id=request.action_instance_id,
        action_contract_address=request.action_contract_address,
        observation_point=(
            request.temporal_contexts[0].observation_point
            if request.temporal_contexts
            else "time.runtime.aptl@segment=0,tick=0"
        ),
        observations=observations or ["legacy bounded smoke action completed"],
        evidence_refs=list(request.evidence_refs),
        diagnostics=[diagnostic.message for diagnostic in execution.diagnostics],
    )
    return ParticipantNativeActionExecution(
        apply_result=ApplyResult(
            success=execution.success,
            # RAES owns participant history and lifecycle projection. The
            # native command result is evidence, not authority to realize
            # action-contract, boundary, instance, or shared-state resources.
            snapshot=snapshot,
            diagnostics=execution.diagnostics,
            changed_addresses=[],
        ),
        action_result=result,
        post_state_digest=request.post_state_digest,
    )
