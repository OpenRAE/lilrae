"""APTL participant runtime built on the RAES-owned lifecycle and commit path."""

from __future__ import annotations

from aptl.backends._raes_participant_legacy import model_legacy_action

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import TYPE_CHECKING, cast

from raes_backend_protocols.participant_runtime_base import BaseParticipantRuntime
from raes_backend_protocols.participant_invocation_tools import (
    ParticipantInvocationToolActionPort,
)
from raes_contracts.contracts import (
    ParticipantDecisionSurfaceSelectionV2Model,
    ParticipantTemporalRuntimeContextModel,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_binding import (
    ParticipantActionAdmissionRequest,
    ParticipantActionApplyResult,
    ParticipantNativeActionExecution,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from aptl.backends.raes_participant_actions import (
    DEFAULT_PARTICIPANT_ACTIONS,
    PARTICIPANT_ACTION_ADDRESS as _PARTICIPANT_ACTION_ADDRESS,
    ParticipantActionSpec,
)
from aptl.backends.raes_participant_provider import (
    ParticipantDecisionSolicitation,
    ParticipantProviderFailure,
    ParticipantSelectionProvider,
    parse_provider_selection,
)

if TYPE_CHECKING:
    from aptl.backends.lilrae_participant_execution import LilraeParticipantBinding
    from aptl.backends.raes_participant_driver import ParticipantPlanAuthority
    from aptl.core.deployment.backend import DeploymentBackend

PARTICIPANT_ACTION_ADDRESS = _PARTICIPANT_ACTION_ADDRESS


class AptlParticipantRuntime(BaseParticipantRuntime):
    """Participant component of APTL's ``full-remote-control-plane`` target.

    The runtime adds APTL's provider mediation and bounded realization layer to
    RAES's canonical participant lifecycle, admission, and history semantics.
    """

    def __init__(
        self,
        *,
        deployment_backend: DeploymentBackend,
        action_specs: Mapping[str, ParticipantActionSpec] | None = None,
        plan_authority: ParticipantPlanAuthority | None = None,
        autonomous_bindings: tuple[LilraeParticipantBinding, ...] = (),
    ) -> None:
        """Initialize bounded provider mediation over the RAES base runtime."""

        super().__init__()
        from aptl.backends.lilrae_participant_execution import (
            LilraeParticipantExecution,
        )

        self.autonomous_execution = LilraeParticipantExecution(autonomous_bindings)
        self.deployment_backend = deployment_backend
        self.action_specs = dict(action_specs or DEFAULT_PARTICIPANT_ACTIONS)
        self.plan_authority = plan_authority
        self.delivery_tools = None
        self._behavior_history: dict[str, list[dict[str, object]]] = {}
        self._selection_provider: ParticipantSelectionProvider | None = None
        self._pending_selections: dict[
            str, ParticipantDecisionSurfaceSelectionV2Model
        ] = {}
        self._pending_selection_episodes: dict[str, tuple[str, str]] = {}
        self._solicitation_counts: dict[tuple[str, str], int] = {}
        self._seen_solicitations: dict[tuple[str, str], set[str]] = {}
        self._in_flight_participants: set[str] = set()
        self._pending_realization_evidence: dict[
            str,
            tuple[Mapping[str, object], Mapping[str, object]],
        ] = {}

    def bind_selection_provider(
        self,
        provider: ParticipantSelectionProvider,
    ) -> None:
        """Bind the management-owned decision source for one governed run."""

        self._selection_provider = provider

    def attach_invocation_tool_actions(
        self, port: ParticipantInvocationToolActionPort
    ) -> None:
        """Pass the runtime-owned port to its exact installed native worker."""
        self.autonomous_execution.attach_tool_port(port)

    def bind_autonomous_action(
        self,
        participant_address: str,
        action_contract_address: str,
        observation_boundary_address: str,
        participant_implementation_ref: str,
        action_instance_id: str,
        temporal_contexts: tuple[ParticipantTemporalRuntimeContextModel, ...],
        snapshot: RuntimeSnapshot,
    ) -> ParticipantActionAdmissionRequest:
        """Resolve only an installed native binding for the RAES scheduler."""
        return self.autonomous_execution.bind(
            participant_address,
            action_contract_address,
            observation_boundary_address,
            participant_implementation_ref,
            action_instance_id,
            temporal_contexts,
        )

    def admit_actions_concurrently(
        self,
        requests: tuple[ParticipantActionAdmissionRequest, ...],
        snapshot: RuntimeSnapshot,
        max_workers: int,
    ) -> tuple[ParticipantActionApplyResult, ...]:
        """Validate every installed binding before RAES dispatches the batch."""
        if not self.autonomous_execution.accepts_batch(requests, max_workers):
            from raes_backend_protocols.participant_action_commit import (
                reject_participant_action_outcome,
            )

            return tuple(
                reject_participant_action_outcome(
                    snapshot,
                    ApplyResult(success=False, snapshot=snapshot),
                    request.participant_address,
                    "lilrae.participant-binding-refused",
                    "Concurrent participant binding was refused.",
                )
                for request in requests
            )
        return super().admit_actions_concurrently(requests, snapshot, max_workers)

    def solicit_selection(
        self,
        request: ParticipantDecisionSolicitation,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Invoke and validate the provider inside a RAES participant operation."""

        budget_key = (request.participant_address, request.episode_id)
        self._prune_solicitation_state(budget_key)
        failure = self._selection_context_failure(request, snapshot, budget_key)
        selection = None
        if failure is None:
            selection, provider_failure = self._invoke_selection_provider(
                request, budget_key
            )
            if selection is None:
                failure = provider_failure or (
                    "participant selection provider failed or returned malformed output"
                )
            elif selection.model_dump(mode="json") not in tuple(
                request.candidate_selections
            ):
                failure = (
                    "participant provider selected outside the delivered candidate set"
                )
        if failure is not None:
            return _selection_failure(
                snapshot,
                request.participant_address,
                failure,
            )
        selection = cast(ParticipantDecisionSurfaceSelectionV2Model, selection)
        self._pending_selections[request.solicitation_id] = selection
        self._pending_selection_episodes[request.solicitation_id] = budget_key
        return ApplyResult(
            success=True,
            snapshot=snapshot,
            # The validated selection is pending backend state until the
            # subsequent RAES admission operation commits a participant
            # history transition.  This solicitation does not alter the
            # portable snapshot and therefore must not report a changed
            # snapshot address (RAES 4.1 contract validation rejects that
            # false transition claim).
            changed_addresses=[],
        )

    def _selection_context_failure(
        self,
        request: ParticipantDecisionSolicitation,
        snapshot: RuntimeSnapshot,
        budget_key: tuple[str, str],
    ) -> str | None:
        """Return the first closed-world admission failure for a solicitation."""

        from aptl.backends.raes_participant_driver import (
            MAX_ADMITTED_PARTICIPANT_ACTIONS,
            MAX_PARTICIPANT_EPISODE_SECONDS,
            MAX_PARTICIPANT_PROPOSALS,
        )

        episode = snapshot.participant_episode_results.get(request.participant_address)
        initialized_at = (
            episode.get("initialized_at") if isinstance(episode, Mapping) else None
        )
        admitted_actions = sum(
            event.get("event_type") == "action_attempted"
            and event.get("episode_id") == request.episode_id
            for event in snapshot.participant_behavior_history.get(
                request.participant_address, ()
            )
        )
        seen = self._seen_solicitations.setdefault(budget_key, set())
        checks = (
            (
                self._selection_provider is None,
                "no participant selection provider is bound",
            ),
            (
                not isinstance(episode, Mapping)
                or episode.get("episode_id") != request.episode_id
                or episode.get("status") != "running",
                "participant selection is outside the active episode",
            ),
            (
                not isinstance(initialized_at, str)
                or _elapsed_seconds(initialized_at) > MAX_PARTICIPANT_EPISODE_SECONDS,
                "participant episode time budget is exhausted",
            ),
            (
                admitted_actions >= MAX_ADMITTED_PARTICIPANT_ACTIONS,
                "participant admitted-action budget is exhausted",
            ),
            (
                self._solicitation_counts.get(budget_key, 0)
                >= MAX_PARTICIPANT_PROPOSALS,
                "participant proposal budget is exhausted",
            ),
            (
                request.participant_address in self._in_flight_participants,
                "participant already has a decision in flight",
            ),
            (
                request.solicitation_id in self._pending_selections
                or request.solicitation_id in seen,
                "participant selection solicitation was replayed",
            ),
        )
        return next((message for failed, message in checks if failed), None)

    def _invoke_selection_provider(
        self,
        request: ParticipantDecisionSolicitation,
        budget_key: tuple[str, str],
    ) -> tuple[ParticipantDecisionSurfaceSelectionV2Model | None, str | None]:
        """Reserve one proposal; return the selection or the runner's failure."""

        seen = self._seen_solicitations.setdefault(budget_key, set())
        seen.add(request.solicitation_id)
        self._solicitation_counts[budget_key] = (
            self._solicitation_counts.get(budget_key, 0) + 1
        )
        self._in_flight_participants.add(request.participant_address)
        selection = None
        failure = None
        try:
            provider = self._selection_provider
            if provider is not None:
                selection = parse_provider_selection(provider.select(request))
        except ParticipantProviderFailure as exc:
            failure = f"participant selection provider failed: {exc}"
        except Exception:
            selection = None
        finally:
            self._in_flight_participants.discard(request.participant_address)
        return selection, failure

    def next_solicitation_ordinal(
        self,
        participant_address: str,
        episode_id: str,
    ) -> int:
        """Return the next bounded proposal ordinal for the active episode."""

        return (
            self._solicitation_counts.get(
                (participant_address, episode_id),
                0,
            )
            + 1
        )

    def _prune_solicitation_state(
        self,
        active_key: tuple[str, str],
    ) -> None:
        """Retain replay state only for the participant's active episode."""

        participant_address, _ = active_key
        stale_keys = {
            key
            for key in self._seen_solicitations
            if key[0] == participant_address and key != active_key
        }
        for key in stale_keys:
            del self._seen_solicitations[key]
            self._solicitation_counts.pop(key, None)
        stale_pending = {
            solicitation_id
            for solicitation_id, key in self._pending_selection_episodes.items()
            if key[0] == participant_address and key != active_key
        }
        for solicitation_id in stale_pending:
            self._pending_selection_episodes.pop(solicitation_id, None)
            self._pending_selections.pop(solicitation_id, None)

    def consume_selection(
        self,
        solicitation_id: str,
    ) -> "ParticipantDecisionSurfaceSelectionV2Model":
        """Consume a successfully mediated selection exactly once."""

        try:
            selection = self._pending_selections.pop(solicitation_id)
        except KeyError as exc:
            raise ValueError(
                "participant selection is unavailable or already consumed"
            ) from exc
        self._pending_selection_episodes.pop(solicitation_id, None)
        return selection

    def admit_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantActionApplyResult:
        """Run the RAES base admission path and retain its authoritative history."""

        if request.execution_scope_ref is not None:
            # Autonomous workers do not own settled history or publication.
            return super().admit_action(request, snapshot)

        try:
            result = super().admit_action(request, snapshot)
        except Exception:
            self._pending_realization_evidence.pop(
                request.action_instance_id,
                None,
            )
            raise
        pending_evidence = self._pending_realization_evidence.pop(
            request.action_instance_id,
            None,
        )
        # The RAES transition is authoritative as soon as the base runtime
        # returns it. Archive publication is a subsequent evidence concern and
        # must never make the caller lose an already accepted state/history cut.
        self._behavior_history = {
            address: [dict(event) for event in events]
            for address, events in result.snapshot.participant_behavior_history.items()
        }
        if (
            result.success
            and result.action_result is not None
            and pending_evidence is not None
            and self.plan_authority is not None
        ):
            from aptl.backends.raes_participant_realizations import (
                _persist_action_evidence,
            )

            evaluator_record, participant_record = pending_evidence
            publication_diagnostics = _persist_action_evidence(
                self.plan_authority,
                evaluator_record=evaluator_record,
                participant_record=participant_record,
            )
            result.diagnostics.extend(publication_diagnostics)
            result.details["evidence_publication"] = {
                "status": ("failed" if publication_diagnostics else "succeeded"),
                "failure_count": len(publication_diagnostics),
            }
        return result

    def behavior_history(self) -> dict[str, list[dict[str, object]]]:
        """Return the most recently committed RAES behavior history."""

        return {
            address: [dict(event) for event in events]
            for address, events in self._behavior_history.items()
        }

    def status(self) -> dict[str, object]:
        """Return a secret-free runtime readiness projection."""

        status = super().status()
        status.update(
            {
                "backend": "aptl",
                "action_participants": sorted(self.action_specs),
                "scenario_source_sha256": (
                    self.plan_authority.scenario_source_sha256
                    if self.plan_authority is not None
                    else None
                ),
                "compiled_model_sha256": (
                    self.plan_authority.compiled_model_sha256
                    if self.plan_authority is not None
                    else None
                ),
                "bounded_participant_agency_ready": bool(
                    self.plan_authority is not None
                    and self.plan_authority.readiness is not None
                ),
            }
        )
        return status

    def _model_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        episode_id: str,
    ) -> ParticipantNativeActionExecution:
        """Dispatch one already-admitted action to its closed APTL realization."""

        if self.delivery_tools is not None:
            return self.delivery_tools.execute(request, snapshot, episode_id)

        if request.execution_scope_ref is not None:
            return self.autonomous_execution.execute(request, snapshot, episode_id)

        if (
            self.plan_authority is not None
            and self.plan_authority.is_approved_bounded_participant_agency
        ):
            from aptl.backends.raes_participant_realizations import (
                execute_participant_realization,
            )

            execution = execute_participant_realization(
                request=request,
                snapshot=snapshot,
                episode_id=episode_id,
                authority=self.plan_authority,
                deployment_backend=self.deployment_backend,
            )
            if (
                execution.evaluator_record is not None
                and execution.participant_record is not None
            ):
                self._pending_realization_evidence[request.action_instance_id] = (
                    execution.evaluator_record,
                    execution.participant_record,
                )
            return execution.native
        return model_legacy_action(
            self.deployment_backend,
            self.action_specs,
            request,
            snapshot,
            episode_id=episode_id,
        )


def _selection_failure(
    snapshot: RuntimeSnapshot,
    participant_address: str,
    message: str,
) -> ApplyResult:
    """Build failure for the bounded participant workflow."""
    return ApplyResult(
        success=False,
        snapshot=snapshot,
        diagnostics=[
            Diagnostic(
                code="aptl.participant-runtime.selection-failed",
                domain="participant",
                address=participant_address,
                message=message,
            )
        ],
    )


def _elapsed_seconds(initialized_at: str) -> float:
    """Handle seconds for the bounded participant workflow."""
    try:
        start = datetime.fromisoformat(initialized_at.replace("Z", "+00:00"))
    except ValueError:
        return float("inf")
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - start).total_seconds()
