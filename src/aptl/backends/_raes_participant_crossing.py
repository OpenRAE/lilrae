"""Crossing-policy realization for SDL-authored participant delivery."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingGateDisposition,
    ParticipantCrossingPolicyReferenceModel,
    ParticipantCrossingSubjectKind,
)
from raes_runtime.participant_crossing_mediation import (
    ParticipantCrossingIntent,
    ParticipantCrossingPolicyResolution,
    ParticipantCrossingSemanticGates,
    ParticipantCrossingValidationContext,
)

from aptl.backends._raes_participant_models import ParticipantInjectTurn
from aptl.workbench.process import AgentExecutionError
from aptl.core.participant_tools.contracts import MAX_TOOL_ACTIONS


class _ParticipantDeliveryCrossingPolicyResolver:
    """Resolve API-423 ingress policy from compiled delivery declarations."""

    def __init__(
        self,
        turns: tuple[ParticipantInjectTurn, ...],
        target: object,
        behavior_specifications: Mapping[str, object],
    ) -> None:
        """Compile stable participant crossing policies for this sequence."""

        self._policies = _delivery_crossing_policies(turns)
        self._actions = {
            participant: frozenset(
                getattr(specification, "action_contract_addresses", ())
            )
            for specification in behavior_specifications.values()
            for participant in specification.participant_addresses
        }
        for participant, policy in tuple(self._policies.items()):
            if self._actions.get(participant):
                turn_count = sum(
                    turn.participant_address == participant for turn in turns
                )
                # Each action retains three behavior records and two crossing
                # records. Each turn also retains two controls and their four
                # crossing records. Control ordinals and history ordinals are
                # distinct; freeze one sufficient interval before any record.
                self._policies[participant] = policy.model_copy(
                    update={
                        "valid_from_order": 0,
                        "valid_until_order": policy.valid_until_order
                        + turn_count * (5 * MAX_TOOL_ACTIONS + 6),
                    }
                )
        self._subjects: list[object] = []
        behavior_evidence, behavior_authority = _participant_behavior_policy_refs(
            turns,
            behavior_specifications,
        )
        self._evidence_refs = frozenset(
            {
                *(
                    ref
                    for turn in turns
                    for ref in (
                        *turn.evidence_requirement_addresses,
                        *turn.control_evidence_addresses,
                    )
                ),
                *behavior_evidence,
                *_target_participant_policy_evidence_refs(target),
            }
        )
        self._authority_refs = (
            frozenset(
                ref
                for turn in turns
                for ref in (
                    turn.controller_address,
                    *turn.control_evidence_addresses,
                )
            )
            | behavior_authority
        )

    def resolve(
        self,
        intent: ParticipantCrossingIntent,
        _snapshot: object,
    ) -> ParticipantCrossingPolicyResolution:
        """Resolve an admitted crossing against its authored policy."""

        policy = self._policies.get(intent.participant_address)
        if policy is None:
            raise ValueError("participant delivery crossing policy is unavailable")
        if (
            intent.subject.subject_kind
            == ParticipantCrossingSubjectKind.PARTICIPANT_ACTION_ADMISSION
        ):
            if intent.action_or_projection_ref not in self._actions.get(
                intent.participant_address, ()
            ):
                raise ValueError("participant delivery action is not authored")
        if intent.subject not in self._subjects:
            self._subjects.append(intent.subject)
        return ParticipantCrossingPolicyResolution(
            policy=policy,
            gates=ParticipantCrossingSemanticGates(
                participant_authority=ParticipantCrossingGateDisposition.PERMIT,
                action_admission=ParticipantCrossingGateDisposition.PERMIT,
                visibility=ParticipantCrossingGateDisposition.NOT_APPLICABLE,
                marking_authorization=ParticipantCrossingGateDisposition.PERMIT,
                declassification=ParticipantCrossingGateDisposition.NOT_APPLICABLE,
                transformation_validity=(
                    ParticipantCrossingGateDisposition.NOT_APPLICABLE
                ),
            ),
            reason_code="authored-participant-delivery-policy-satisfied",
        )

    def validation_context(
        self,
        _snapshot: object,
        _participant_address: str,
    ) -> ParticipantCrossingValidationContext:
        """Return the closed evidence and authority validation context."""

        return ParticipantCrossingValidationContext(
            known_subjects=tuple(self._subjects),
            policies=tuple(self._policies.values()),
            known_evidence_refs=self._evidence_refs,
            known_authority_basis_refs=self._authority_refs,
        )


def _target_participant_policy_evidence_refs(target: object) -> tuple[str, ...]:
    """Return the target's own evidence for supported participant policy."""

    manifest = getattr(target, "manifest", None)
    capabilities = getattr(manifest, "participant_runtime", None)
    return tuple(
        ref
        for support in getattr(capabilities, "feature_support", ()) or ()
        for ref in getattr(support, "evidence_refs", ()) or ()
    )


def _participant_behavior_policy_refs(
    turns: tuple[ParticipantInjectTurn, ...],
    behavior_specifications: Mapping[str, object],
) -> tuple[frozenset[str], frozenset[str]]:
    """Collect compiled state and transition evidence for delivered participants."""

    admitted = {turn.behavior_specification_address for turn in turns}
    evidence: set[str] = set()
    authority: set[str] = set()
    for address in admitted:
        behavior = behavior_specifications.get(address)
        if behavior is None:
            continue
        for state in getattr(behavior, "controller_states", ()):
            evidence.update(getattr(state, "evidence_addresses", ()) or ())
            authority.update(
                getattr(state, "authority_basis_addresses", ())
                or getattr(state, "authority_basis_refs", ())
                or ()
            )
        for transition in getattr(behavior, "control_transitions", ()):
            evidence.update(getattr(transition, "evidence_addresses", ()) or ())
            evidence.update(
                getattr(transition, "completion_evidence_addresses", ()) or ()
            )
    return frozenset(evidence), frozenset(authority)


def _delivery_crossing_policies(
    turns: tuple[ParticipantInjectTurn, ...],
) -> dict[str, ParticipantCrossingPolicyReferenceModel]:
    """Build one stable authored policy interval for each participant."""

    grouped: dict[str, list[ParticipantInjectTurn]] = {}
    for turn in turns:
        grouped.setdefault(turn.participant_address, []).append(turn)
    policies: dict[str, ParticipantCrossingPolicyReferenceModel] = {}
    for participant, participant_turns in grouped.items():
        coordinates = {
            (
                turn.policy_ref,
                turn.policy_revision,
                turn.exposure_policy_ref,
                turn.audience_scope_ref,
                turn.visibility_basis_ref,
                turn.disclosure_basis_ref,
                turn.observation_boundary_address,
            )
            for turn in participant_turns
        }
        if len(coordinates) != 1:
            raise AgentExecutionError(
                "participant delivery policy changes within one participant sequence"
            )
        (
            policy_ref,
            policy_revision,
            exposure_policy_ref,
            audience_scope_ref,
            visibility_basis_ref,
            disclosure_basis_ref,
            observation_boundary_address,
        ) = coordinates.pop()
        policy_payload = json.dumps(
            {
                "audience_scope_ref": audience_scope_ref,
                "disclosure_basis_ref": disclosure_basis_ref,
                "exposure_policy_ref": exposure_policy_ref,
                "observation_boundary_address": observation_boundary_address,
                "policy_ref": policy_ref,
                "policy_revision": policy_revision,
                "visibility_basis_ref": visibility_basis_ref,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        valid_from = min(turn.control_valid_from_order for turn in participant_turns)
        # API-423 records a request at the control transition's logical order
        # and its decision at the following order.  The authored control window
        # therefore supplies the policy's request interval; extend the policy
        # by one order so the terminal decision remains inside that policy.
        valid_until = (
            max(turn.control_valid_until_order for turn in participant_turns) + 1
        )
        policies[participant] = ParticipantCrossingPolicyReferenceModel(
            policy_id=policy_ref,
            policy_revision=policy_revision,
            policy_digest=f"sha256:{hashlib.sha256(policy_payload).hexdigest()}",
            policy_decision_ref=disclosure_basis_ref,
            decision_cut_ref=observation_boundary_address,
            effective_order=valid_from,
            valid_from_order=valid_from,
            valid_until_order=valid_until,
        )
    return policies


def participant_runtime_options(
    plan: object | None, target: object
) -> dict[str, object]:
    """Return the participant configuration of the one runtime for a run.

    RAES fixes participant behavior and crossing policy when the runtime is
    built, and the same runtime later delivers every participant turn
    (OpenRAE/rae#1660). A run without participant deliveries needs none.
    """

    turns = tuple(getattr(plan, "turns", ()) or ())
    behavior = getattr(plan, "behavior_specifications", None)
    if not turns or not behavior:
        return {}
    return {
        "behavior_specifications": behavior,
        "crossing_policy_resolver": _ParticipantDeliveryCrossingPolicyResolver(
            turns, target, behavior
        ),
        "enforce_final_sink_flow_control": False,
    }
