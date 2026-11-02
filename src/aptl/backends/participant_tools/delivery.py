"""Sequential MCP actions admitted by the run's existing RAES control plane."""

from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Event, RLock
from typing import Protocol, TYPE_CHECKING
from uuid import uuid4

from raes_contracts.satisfiability import canonical_contract_digest
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    ParticipantActionResultModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
)
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.participant_native_execution import ParticipantNativeActionExecution
from raes_contracts.runtime_state import ApplyResult, OperationState, RuntimeSnapshot

from aptl.backends.participant_tools.session import detach_tool_json, tool_result_failed
from aptl.backends.participant_tools.transport import LilraeToolTransport
from aptl.core.agent_errors import AgentExecutionError
from aptl.core.mcp_results import redact_mcp_result
from aptl.core.participant_tools.contracts import MAX_TOOL_ACTIONS


if TYPE_CHECKING:
    from raes_runtime.control_plane import RuntimeControlPlane
    from raes_runtime.control_plane_security import ControlPlaneIdentity
    from raes_runtime.participant_crossing_mediation import ParticipantCrossingEvidence
    from raes_processor.models import ParticipantBehaviorRuntime


class DeliveryTurn(Protocol):
    """Admitted turn coordinates needed by the native tool adapter."""

    participant_address: str
    observation_boundary_address: str
    address: str


class DeliveryRuntime(Protocol):
    """The existing runtime's currently installed native callback."""

    delivery_tools: DeliveryToolSession | None


_REFUSED = "Participant tool call refused."
_UNKNOWN = "Participant tool outcome is unknown."


@dataclass(frozen=True)
class _TransportBinding:
    """Carrier limits for an already selected profile server."""

    server_id: str
    execution_binding: _ExecutionLimit


@dataclass(frozen=True)
class _ExecutionLimit:
    """A carrier deadline; it grants no participant authority."""

    timeout_seconds: float


@dataclass(eq=False)
class DeliveryToolCall:
    """Local rendezvous between an admitted action and its MCP handler."""

    request: ParticipantActionAdmissionRequest
    server: str
    tool: str
    granted: Event = field(default_factory=Event)
    completed: Event = field(default_factory=Event)
    future: Future[None] | None = None
    outcome: str = "unknown"
    dispatched: bool = False
    settled: bool = False


def _apparatus(
    turn: DeliveryTurn,
) -> tuple[
    ParticipantImplementationManifestModel, ParticipantImplementationSelectionModel
]:
    """Describe the installed host adapter using the public RAES contracts."""
    contracts = [
        "participant-episode-state-envelope-v1",
        "participant-episode-history-event-stream-v1",
        "participant-behavior-history-event-stream-v1",
    ]
    manifest = ParticipantImplementationManifestModel.model_validate(
        {
            "identity": {"name": "claude-code-host", "version": "1.0.0"},
            "implementation_kind": "agent",
            "supported_contract_versions": [
                "participant-implementation-manifest-v1",
                "participant-implementation-provenance-v1",
                *contracts,
            ],
            "compatibility": {"participant_runtimes": ["aptl-participant-runtime"]},
            "concept_bindings": [
                {"scope": scope, "family": family}
                for scope, family in (
                    ("implementation_kind", "apparatus-declarations"),
                    (
                        "capabilities.supported_participant_contracts",
                        "apparatus-declarations",
                    ),
                    (
                        "capabilities.supported_decision_surface_modes",
                        "apparatus-declarations",
                    ),
                    (
                        "capabilities.tool_affordance_expectations",
                        "tools-and-artifacts",
                    ),
                    ("capabilities.exposure_policy_kinds", "provenance-and-evidence"),
                )
            ],
            "constraints": {
                "action_execution": "one admitted MCP call at a time during a LilRAE delivery",
                "action_semantics": "authored call contract; arguments and effects are not interpreted",
            },
            "capabilities": {
                "supported_participant_contracts": contracts,
                "supported_decision_surface_modes": ["autonomous"],
                "tool_affordance_expectations": ["x-lilrae:profile-tools"],
                "exposure_policy_kinds": ["observation-stream"],
            },
        }
    )
    selection = ParticipantImplementationSelectionModel.model_validate(
        {
            "participant_address": turn.participant_address,
            "implementation_identity": manifest.identity,
            "manifest_ref": "participant-implementation-manifest:claude-code",
            "manifest_digest": canonical_contract_digest(manifest),
            "selected_decision_surface_mode": "autonomous",
            "participant_contract_versions": contracts,
            "exposure_policy": {
                "policy_id": turn.observation_boundary_address,
                "policy_version": "1",
                "policy_digest": canonical_json_digest(
                    {"boundary": turn.observation_boundary_address}
                ),
                "exposure_policy_kinds": ["observation-stream"],
                "disclosed_refs": [],
                "withheld_refs": [],
                "tool_affordance_refs": [],
                "visibility_scope_refs": [turn.observation_boundary_address],
            },
        }
    )
    return manifest, selection


@dataclass(frozen=True)
class DeliveryActionAuthority:
    """Management-owned identity and crossing evidence for one delivered turn."""

    identity: ControlPlaneIdentity
    crossing_evidence: ParticipantCrossingEvidence


class DeliveryToolSession:
    """One delivered turn, one live participant episode, and no parallel actions.

    The admission worker reaches the runtime's native callback only after RAES
    accepts the action and crossing. That callback releases the waiting MCP
    handler and waits for its outcome. RAES then commits its own history before
    the carrier returns the tool result. No runtime lock is acquired by the MCP
    completion path.
    """

    def __init__(
        self,
        *,
        control_plane: RuntimeControlPlane,
        runtime: DeliveryRuntime,
        behavior: ParticipantBehaviorRuntime,
        turn: DeliveryTurn,
        authority: DeliveryActionAuthority,
        tools: Mapping[str, tuple[str, ...]],
        timeout_seconds: float = 600.0,
    ) -> None:
        if (
            len(behavior.action_contract_addresses) != 1
            or behavior.temporally_bound_action_addresses
            or turn.observation_boundary_address
            not in behavior.observation_boundary_addresses
            or runtime.delivery_tools is not None
        ):
            raise AgentExecutionError(_REFUSED)
        self.control_plane = control_plane
        self.runtime = runtime
        self.behavior = behavior
        self.turn = turn
        self.identity = authority.identity
        self.crossing_evidence = authority.crossing_evidence
        self.timeout_seconds = timeout_seconds
        self.manifest, self.selection = _apparatus(turn)
        self._tools = {server: frozenset(names) for server, names in tools.items()}
        self.bindings = tuple(
            _TransportBinding(server, _ExecutionLimit(timeout_seconds))
            for server in tools
        )
        self.cancellation = Event()
        self.uncertain = False
        self.invocation_action_instance_id = str(uuid4())
        self._lock = RLock()
        self._seen: set[tuple[str, str]] = set()
        self._active: DeliveryToolCall | None = None
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="participant-tool"
        )
        runtime.delivery_tools = self

    def transport(self) -> LilraeToolTransport:
        """Reuse the authenticated common MCP carrier."""
        return LilraeToolTransport(self)

    def begin(
        self,
        server: str,
        tool: str,
        arguments: dict[str, object],
        call_id: str,
        *,
        configuration: Mapping[str, object] | None = None,
    ) -> DeliveryToolCall:
        """Ask RAES to admit the exact profile call before returning dispatch."""
        detach_tool_json(arguments)
        detach_tool_json(dict(configuration) if configuration is not None else {})
        if not isinstance(call_id, str) or not 1 <= len(call_id) <= 128:
            raise AgentExecutionError(_REFUSED)
        with self._lock:
            key = (server, call_id)
            if (
                self.cancellation.is_set()
                or self._active is not None
                or len(self._seen) >= MAX_TOOL_ACTIONS
                or key in self._seen
                or tool not in self._tools.get(server, ())
            ):
                raise AgentExecutionError(_REFUSED)
            self._seen.add(key)
            request = ParticipantActionAdmissionRequest(
                participant_address=self.turn.participant_address,
                action_contract_address=self.behavior.action_contract_addresses[0],
                observation_boundary_address=self.turn.observation_boundary_address,
                action_instance_id=str(uuid4()),
                implementation_manifest=self.manifest,
                implementation_selection=self.selection,
            )
            call = DeliveryToolCall(request, server, tool)
            self._active = call
            call.future = self._executor.submit(self._submit, call)
        if not call.granted.wait(self.timeout_seconds) or not call.dispatched:
            self.unknown(call)
            raise AgentExecutionError(_REFUSED)
        return call

    def _submit(self, call: DeliveryToolCall) -> None:
        """Submit through RAES's incumbent action and crossing owners."""
        try:
            receipt = self.control_plane.admit_participant_action(
                self.behavior,
                call.request,
                identity=self.identity,
                crossing_evidence=self.crossing_evidence,
                idempotency_key=call.request.action_instance_id,
            )
            status = self.control_plane.get_operation(receipt.operation_id)
            if status is None or status.state is not OperationState.SUCCEEDED:
                raise AgentExecutionError(_REFUSED)
        finally:
            call.granted.set()

    def execute(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        episode_id: str,
    ) -> ParticipantNativeActionExecution:
        """Run only the exact request waiting on this management-owned session."""
        call = self._active
        if call is None or request != call.request or self.cancellation.is_set():
            raise AgentExecutionError(_REFUSED)
        call.dispatched = True
        call.granted.set()
        if not call.completed.wait(self.timeout_seconds):
            self.uncertain = True
            self.cancellation.set()
        outcome = call.outcome
        result = ParticipantActionResultModel(
            status=outcome,
            failure_class={"unknown": "unknown", "failed": "backend_error"}.get(
                outcome
            ),
            participant_address=request.participant_address,
            episode_id=episode_id,
            action_instance_id=request.action_instance_id,
            action_contract_address=request.action_contract_address,
            observation_point=self.turn.address,
            observations=[f"{call.server}/{call.tool}: {outcome}"],
        )
        return ParticipantNativeActionExecution(
            apply_result=ApplyResult(success=True, snapshot=snapshot),
            action_result=result,
        )

    def complete(
        self, call: DeliveryToolCall, result: Mapping[str, object]
    ) -> dict[str, object]:
        """Release data only after the accepted outcome is in RAES history."""
        try:
            detached, _ = detach_tool_json(result)
            failed = tool_result_failed(detached)
            safe = redact_mcp_result(detached, call.server, call.tool)
            self._settle(call, "failed" if failed else "succeeded")
            return safe
        except Exception:
            self.unknown(call)
            raise AgentExecutionError(_UNKNOWN) from None

    def _settle(self, call: DeliveryToolCall, outcome: str) -> None:
        with self._lock:
            if self._active is not call or call.settled or self.cancellation.is_set():
                raise AgentExecutionError(_REFUSED)
            call.outcome = outcome
            call.completed.set()
        call.future.result(timeout=self.timeout_seconds)
        with self._lock:
            call.settled = True
            self._active = None

    def unknown(self, call: DeliveryToolCall) -> None:
        """Retain an unknown outcome and prohibit further calls in this turn."""
        with self._lock:
            if self._active is not call or call.settled:
                return
            self.cancellation.set()
            self.uncertain = call.dispatched
            call.outcome = "unknown"
            call.completed.set()
        try:
            call.future.result(timeout=self.timeout_seconds)
        except Exception:
            pass
        call.settled = True

    def close(self) -> None:
        """Drain the action before detaching its native realization callback."""
        self.cancellation.set()
        if self._active is not None:
            self.unknown(self._active)
        self._executor.shutdown(wait=True)
        self.runtime.delivery_tools = None
