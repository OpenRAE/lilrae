"""Installed native bindings for RAES-owned autonomous participant execution."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from threading import Condition, Event

from raes_backend_protocols.capabilities import ParticipantExecutionBinding
from raes_contracts.contracts import (
    ParticipantActionResultModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
    ParticipantTemporalRuntimeContextModel,
)
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.participant_native_execution import ParticipantNativeActionExecution
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_contracts.satisfiability import canonical_contract_digest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_configuration import (
    validate_participant_configuration_selection,
)

from aptl.utils.redaction import redact
from aptl.workbench.process import (
    AgentExecutionError,
    BoundedProcessError,
    REASON_TIMEOUT,
    REASON_CANCELLED,
)

MAX_CONCURRENT_PARTICIPANTS = 8


@dataclass(frozen=True)
class LilraeParticipantBinding:
    """Trusted installed executor for one exact participant/action relation.

    The callable receives only its action identity and cancellation signal.
    It owns bounded native execution, including its configured prompt and model.
    It never receives another participant's snapshot or executor.
    """

    implementation_manifest: ParticipantImplementationManifestModel
    implementation_selection: ParticipantImplementationSelectionModel
    observation_boundary_address: str
    execution_binding: ParticipantExecutionBinding
    executor: Callable[[str, Event], str] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        selection = self.implementation_selection
        manifest = self.implementation_manifest
        if (
            selection.implementation_identity != manifest.identity
            or selection.manifest_digest != canonical_contract_digest(manifest)
            or selection.manifest_ref
            != self.execution_binding.participant_implementation_ref
            or selection.selected_decision_surface_mode != "autonomous"
            or not self.observation_boundary_address.startswith(
                "participant.observation-boundary."
            )
            or not callable(self.executor)
        ):
            raise ValueError("participant implementation binding is inconsistent")
        if self.execution_binding.max_in_flight > MAX_CONCURRENT_PARTICIPANTS:
            raise ValueError("participant binding exceeds native capacity")
        if self.execution_binding.max_retries != 0:
            raise ValueError("native participant retries are not supported")
        configuration = getattr(self.executor, "configuration_result", None)
        if manifest.configuration_registry is not None and configuration is None:
            raise ValueError(
                "participant configuration result is required by its manifest"
            )
        if configuration is not None:
            validate_participant_configuration_selection(selection, configuration)
        if (
            hasattr(self.executor, "timeout_seconds")
            and self.executor.timeout_seconds > self.execution_binding.timeout_seconds
        ):
            raise ValueError("participant executor exceeds the admitted timeout")


class LilraeParticipantExecution:
    """Native reservations and cancellation, below the portable scheduler."""

    def __init__(self, bindings: tuple[LilraeParticipantBinding, ...]) -> None:
        self.bindings = tuple(
            LilraeParticipantBinding(
                implementation_manifest=deepcopy(item.implementation_manifest),
                implementation_selection=deepcopy(item.implementation_selection),
                observation_boundary_address=item.observation_boundary_address,
                execution_binding=deepcopy(item.execution_binding),
                executor=item.executor,
            )
            for item in bindings
        )
        self._by_key = {
            (
                item.implementation_selection.participant_address,
                item.execution_binding.action_contract_address,
            ): item
            for item in self.bindings
        }
        if len(self._by_key) != len(self.bindings):
            raise ValueError("duplicate participant action binding")
        manifests = {}
        for item in self.bindings:
            ref = item.implementation_selection.manifest_ref
            if ref in manifests and manifests[ref] != item.implementation_manifest:
                raise ValueError(
                    "one manifest reference cannot name different implementations"
                )
            manifests[ref] = item.implementation_manifest
        self._condition = Condition()
        self._active: dict[str, tuple[str, Event]] = {}
        self._seen: set[str] = set()
        self._cancelled: set[str] = set()
        self._closed = False

    def planning_diagnostics(self, model) -> list[Diagnostic]:
        """Check each participant against its installed offer before provisioning."""
        diagnostics = []
        for specification in model.behavior_specifications.values():
            policy = specification.autonomous_execution
            if policy is None:
                continue
            for participant in policy.participant_addresses:
                if not self._supports_policy(participant, policy):
                    diagnostics.append(
                        Diagnostic(
                            code="lilrae.participant-binding-refused",
                            domain="participant",
                            address=participant,
                            message="Autonomous policy does not match the participant's installed binding.",
                        )
                    )
        return diagnostics

    def _supports_policy(self, participant, policy) -> bool:
        for action in policy.execution_bindings:
            item = self._by_key.get((participant, action.action_contract_address))
            if item is None:
                return False
            offer = item.execution_binding
            if (
                item.observation_boundary_address != policy.observation_boundary_address
                or offer.participant_implementation_ref
                != policy.participant_implementation_ref
                or offer.target_addresses != action.target_addresses
                or offer.max_action_attempts < action.max_action_attempts
                or offer.max_in_flight < action.max_in_flight
                or not set(policy.temporal_constraint_addresses).issubset(
                    offer.constraint_refs
                )
            ):
                return False
        return True

    def bind(
        self,
        participant: str,
        action: str,
        boundary: str,
        implementation: str,
        action_id: str,
        temporal: tuple[ParticipantTemporalRuntimeContextModel, ...],
        snapshot: RuntimeSnapshot,
    ) -> ParticipantActionAdmissionRequest:
        item = self._by_key.get((participant, action))
        if (
            item is None
            or boundary != item.observation_boundary_address
            or implementation != item.implementation_selection.manifest_ref
        ):
            raise ValueError("autonomous participant binding is not installed")
        return ParticipantActionAdmissionRequest(
            participant_address=participant,
            action_contract_address=action,
            observation_boundary_address=boundary,
            action_instance_id=action_id,
            implementation_manifest=deepcopy(item.implementation_manifest),
            implementation_selection=deepcopy(item.implementation_selection),
            temporal_contexts=temporal,
        )

    def execute(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        episode_id: str,
    ) -> ParticipantNativeActionExecution:
        item = self._by_key.get(
            (request.participant_address, request.action_contract_address)
        )
        if item is None or not self._matches(item, request):
            return self._outcome(
                request,
                snapshot,
                episode_id,
                "authority_denied",
                "Native participant binding was refused.",
            )
        event = Event()
        with self._condition:
            if (
                self._closed
                or request.participant_address in self._cancelled
                or request.action_instance_id in self._seen
                or len(self._active) >= MAX_CONCURRENT_PARTICIPANTS
                or any(
                    participant == request.participant_address
                    for participant, _ in self._active.values()
                )
            ):
                return self._outcome(
                    request,
                    snapshot,
                    episode_id,
                    "authority_denied",
                    "Native participant reservation was refused.",
                )
            self._seen.add(request.action_instance_id)
            self._active[request.action_instance_id] = (
                request.participant_address,
                event,
            )
        try:
            output = item.executor(request.action_instance_id, event)
            if event.is_set():
                return self._outcome(
                    request,
                    snapshot,
                    episode_id,
                    "backend_error",
                    "Participant invocation was cancelled.",
                )
            if not isinstance(output, str) or len(output) > 128_000:
                raise ValueError("invalid native output")
            return self._outcome(request, snapshot, episode_id, None, redact(output))
        except BoundedProcessError as exc:
            if exc.cleanup.residual:
                return self._unknown_outcome(request, snapshot)
            failure = "timeout" if exc.reason == REASON_TIMEOUT else "backend_error"
            return self._outcome(
                request, snapshot, episode_id, failure, exc.stable_summary()
            )
        except AgentExecutionError as exc:
            if event.is_set() and str(exc) == REASON_CANCELLED:
                return self._outcome(
                    request,
                    snapshot,
                    episode_id,
                    "backend_error",
                    "Participant invocation was cancelled before launch.",
                )
            return self._unknown_outcome(request, snapshot)
        except Exception:
            # Native effects may have occurred. No fabricated terminal action
            # result: RAES retains indeterminate-work ownership and peer results.
            return self._unknown_outcome(request, snapshot)
        finally:
            with self._condition:
                self._active.pop(request.action_instance_id, None)
                self._condition.notify_all()

    @staticmethod
    def _unknown_outcome(
        request: ParticipantActionAdmissionRequest, snapshot: RuntimeSnapshot
    ) -> ParticipantNativeActionExecution:
        return ParticipantNativeActionExecution(
            apply_result=ApplyResult(
                success=False,
                snapshot=snapshot,
                diagnostics=[
                    Diagnostic(
                        code="lilrae.participant-native-outcome-unknown",
                        domain="participant",
                        address=request.participant_address,
                        message="Participant invocation has no trustworthy terminal outcome.",
                    )
                ],
            )
        )

    def accepts(self, request: ParticipantActionAdmissionRequest) -> bool:
        """Check an exact binding before any member of a batch starts."""
        item = self._by_key.get(
            (request.participant_address, request.action_contract_address)
        )
        return item is not None and self._matches(item, request)

    def accepts_batch(
        self, requests: tuple[ParticipantActionAdmissionRequest, ...], max_workers: int
    ) -> bool:
        """Reject duplicate participants and oversize batches before dispatch."""
        return (
            2 <= max_workers <= MAX_CONCURRENT_PARTICIPANTS
            and len(requests) <= max_workers
            and len({request.participant_address for request in requests})
            == len(requests)
            and len({request.action_instance_id for request in requests})
            == len(requests)
            and all(self.accepts(request) for request in requests)
        )

    @staticmethod
    def _matches(
        item: LilraeParticipantBinding, request: ParticipantActionAdmissionRequest
    ) -> bool:
        return (
            request.observation_boundary_address == item.observation_boundary_address
            and request.implementation_manifest == item.implementation_manifest
            and request.implementation_selection == item.implementation_selection
            and tuple(request.target_addresses)
            == item.execution_binding.target_addresses
            and bool(request.temporal_contexts)
            and {context.temporal_contract_id for context in request.temporal_contexts}
            == set(item.execution_binding.constraint_refs)
            and request.execution_scope_ref is not None
            and request.execution_generation is not None
        )

    @staticmethod
    def _outcome(
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        episode_id: str,
        failure: str | None,
        observation: str,
    ) -> ParticipantNativeActionExecution:
        result = ParticipantActionResultModel(
            status="failed" if failure else "succeeded",
            failure_class=failure,
            participant_address=request.participant_address,
            episode_id=episode_id,
            action_instance_id=request.action_instance_id,
            action_contract_address=request.action_contract_address,
            observation_point=request.temporal_contexts[0].observation_point
            if request.temporal_contexts
            else "unavailable",
            observations=[observation],
            evidence_refs=list(request.evidence_refs),
        )
        # Native outcome failure is distinct from failure to admit its record.
        return ParticipantNativeActionExecution(
            apply_result=ApplyResult(success=True, snapshot=snapshot),
            action_result=result,
        )

    def cancel(self, participant_address: str | None = None) -> None:
        """Signal owned work; callers must drain before finalizing evidence."""
        with self._condition:
            if participant_address is None:
                self._closed = True
            else:
                self._cancelled.add(participant_address)
            for participant, event in self._active.values():
                if participant_address is None or participant == participant_address:
                    event.set()

    @property
    def trial_cancelled(self) -> bool:
        """Whether the owner requested cancellation of the whole trial."""
        with self._condition:
            return self._closed

    def drain(self, timeout_seconds: float) -> bool:
        """Wait for all invocation cleanup without holding workers' locks."""
        with self._condition:
            return self._condition.wait_for(lambda: not self._active, timeout_seconds)
