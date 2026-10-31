"""Declare only the autonomous bindings installed on this runtime target."""

from dataclasses import replace

from raes_backend_protocols.capabilities import (
    ParticipantRuntimeCapabilities,
    TimeCapabilities,
    TIME_CAPABILITY_REQUIRED_CONTRACTS,
    ParticipantFeatureSupport,
)
from raes_contracts.contracts.participant_invocation_tools import (
    ParticipantInvocationToolActionCapabilitiesModel,
)
from raes_contracts.contracts.participant_tool_support import (
    ParticipantToolProfilesModel,
)
from raes_contracts.manifest_authority import (
    PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS,
)

from aptl.backends.lilrae_participant_execution import (
    LilraeParticipantBinding,
    LilraeParticipantExecution,
    MAX_CONCURRENT_PARTICIPANTS,
)
from aptl.backends.lilrae_participant_tools import (
    MAX_TOOL_ACTIONS,
    MAX_CONCURRENT_TOOLS,
)


def autonomous_manifest_options(
    contracts: frozenset[str],
    participant: ParticipantRuntimeCapabilities,
    options: dict[str, object],
    bindings: tuple[LilraeParticipantBinding, ...],
) -> tuple[frozenset[str], ParticipantRuntimeCapabilities, dict[str, object]]:
    """Add bounded autonomous and shared-time claims for installed executors."""
    if not bindings:
        return contracts, participant, options
    installed = LilraeParticipantExecution(bindings).bindings
    # One portable offer may serve distinct participants. Tool admission must
    # see one exact offer rather than a duplicate per controller or role.
    tools = tuple(tool for item in installed for tool in item.tool_bindings)
    tool_offers = tuple(dict.fromkeys(tool.execution_binding for tool in tools))
    offers = (*tuple(item.execution_binding for item in installed), *tool_offers)
    participant = replace(
        participant,
        supported_behavior_features=participant.supported_behavior_features
        | {"autonomous_execution", "temporal_contracts"},
        supports_autonomous_execution=True,
        supported_autonomous_selection_strategies=frozenset({"ordered_cycle"}),
        supported_autonomous_policy_profiles=frozenset(
            {"participant-autonomous-execution/v1"}
        ),
        supported_autonomous_action_contracts=frozenset(
            item.action_contract_address for item in offers
        ),
        supported_autonomous_target_addresses=frozenset(
            address for item in offers for address in item.target_addresses
        ),
        supported_autonomous_observation_boundaries=frozenset(
            item.observation_boundary_address for item in (*installed, *tools)
        ),
        execution_bindings=offers,
        max_autonomous_participants=min(
            len(
                {
                    item.implementation_selection.participant_address
                    for item in installed
                }
            ),
            MAX_CONCURRENT_PARTICIPANTS,
        ),
        max_autonomous_action_attempts=max(item.max_action_attempts for item in offers),
        max_autonomous_in_flight=MAX_CONCURRENT_PARTICIPANTS,
        max_autonomous_occurrences=max(item.max_action_attempts for item in offers),
        max_autonomous_retries_per_occurrence=0,
        max_autonomous_burst_size=1,
        supports_bounded_concurrency=True,
        max_concurrent_actions=MAX_CONCURRENT_PARTICIPANTS,
    )
    if tools:
        features = frozenset(
            {"tool_affordances", "preconditions", "effects", "failure_classes"}
        )
        participant = replace(
            participant,
            supported_behavior_features=participant.supported_behavior_features
            | features,
            feature_support=(
                *participant.feature_support,
                *(
                    ParticipantFeatureSupport(
                        feature=feature,
                        support_level="exact",
                        evidence_refs=("evidence:lilrae:installed-tool-contract",),
                    )
                    for feature in sorted(features)
                ),
            ),
            tool_profiles=ParticipantToolProfilesModel(
                semantic_versions=["participant-tool-profile/v1"]
            ),
            invocation_tool_actions=ParticipantInvocationToolActionCapabilitiesModel(
                semantic_versions=["participant-invocation-tool-actions/v1"],
                max_tool_actions_per_invocation=MAX_TOOL_ACTIONS,
                max_concurrent_tool_actions_per_invocation=MAX_CONCURRENT_TOOLS,
            ),
        )
    for terms in PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS.values():
        for feature in participant.supported_behavior_features:
            contracts |= terms.get(feature, frozenset())
    time = TimeCapabilities(
        name="lilrae-participant-shared-time",
        supported_contract_versions=TIME_CAPABILITY_REQUIRED_CONTRACTS,
        supported_domain_kinds=frozenset({"simulated"}),
        supported_authority_kinds=frozenset({"runtime"}),
        supported_advancement_modes=frozenset({"stepped"}),
        supported_synchronization_modes=frozenset({"barrier"}),
        supported_constraint_kinds=frozenset({"cadence", "window"}),
        supported_reset_behaviors=frozenset({"unsupported"}),
        supported_replay_behaviors=frozenset({"unsupported"}),
        supports_pause=True,
        supports_append_only_history=True,
        supports_run_provenance=True,
        max_time_domains=1,
        max_clocks=1,
    )
    return (
        contracts | TIME_CAPABILITY_REQUIRED_CONTRACTS,
        participant,
        {**options, "time": time},
    )
