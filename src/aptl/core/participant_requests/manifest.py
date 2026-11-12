"""RAES manifest assembly shared by installed participant implementations."""

from collections.abc import Mapping

from raes_contracts.contracts import (
    ConfigurationTargetRegistryModel,
    ParticipantImplementationManifestModel,
)


def participant_manifest(
    *,
    name: str,
    version: str,
    decision_only: bool,
    constraints: Mapping[str, str],
    registry: ConfigurationTargetRegistryModel | None = None,
) -> ParticipantImplementationManifestModel:
    """Keep tool capabilities separate from request configuration targets."""
    contracts = [
        "participant-episode-state-envelope-v1",
        "participant-episode-history-event-stream-v1",
        "participant-behavior-history-event-stream-v1",
    ]
    if decision_only:
        contracts.append("participant-decision-surface-v2")
    scopes = (
        ("implementation_kind", "apparatus-declarations"),
        ("capabilities.supported_participant_contracts", "apparatus-declarations"),
        ("capabilities.supported_decision_surface_modes", "apparatus-declarations"),
        ("capabilities.tool_affordance_expectations", "tools-and-artifacts"),
        ("capabilities.exposure_policy_kinds", "provenance-and-evidence"),
    )
    return ParticipantImplementationManifestModel.model_validate(
        {
            "identity": {"name": name, "version": version},
            "implementation_kind": "agent",
            "supported_contract_versions": [
                "participant-implementation-manifest-v1",
                "participant-implementation-provenance-v1",
                "experiment-binding-descriptors-v1",
                "participant-configuration-result-v1",
                *contracts,
            ],
            "compatibility": {
                "participant_runtimes": ["aptl"],
                "processors": ["raes-reference-processor"],
                "backends": ["aptl"],
            },
            "concept_bindings": [
                {"scope": scope, "family": family} for scope, family in scopes
            ],
            "constraints": dict(constraints),
            "capabilities": {
                "supported_participant_contracts": contracts,
                "supported_decision_surface_modes": ["autonomous"],
                "tool_affordance_expectations": [
                    "x-aptl:no-action-tools"
                    if decision_only
                    else "x-lilrae:verified-workbench-profile"
                ],
                "exposure_policy_kinds": ["task-statement", "observation-stream"],
            },
            "configuration_registry": registry,
        }
    )
