"""Installed mappings and effect enforcement over a RAES-issued tool port."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from hashlib import sha256
import json
import re
from threading import Event as Cancellation, RLock

import rfc8785
from raes_backend_protocols.participant_invocation_tools import (
    ParticipantInvocationToolActionPort,
)
from raes_contracts.contracts import ParticipantActionResultModel
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.participant_tool_actions import ParticipantToolActionRequest

from aptl.core.participant_tools.model import (
    ActionState,
    Event,
    Phase,
    advance,
)
from aptl.core.mcp_results import redact_mcp_result
from aptl.core.agent_errors import AgentExecutionError
from aptl.core.participant_tools.contracts import (
    LilraeToolBinding,
    LilraeToolCall,
    MAX_TOOL_ACTIONS,
    MAX_CONCURRENT_TOOLS,
    MAX_TOOL_FRAME,
)
from aptl.backends.participant_tools.transport import LilraeToolTransport

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_REFUSED = "Participant tool call refused."
_UNKNOWN = "Participant tool outcome is unknown."


def _detached_json(value: object) -> tuple[object, bytes]:
    """Bound and detach a value in the canonical JSON domain."""
    data = rfc8785.dumps(value)
    if len(data) > MAX_TOOL_FRAME:
        raise ValueError("participant tool frame limit exceeded")
    return json.loads(data), data


def _result_failed(result: dict[str, object]) -> bool:
    """Read the common handlers' explicit result, never infer effects from prose."""
    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise ValueError("invalid participant tool result")
    failed = result.get("isError") is True
    for block in content:
        failed |= _payload_failed(block)
    return failed


def _payload_failed(block: object) -> bool:
    """Read explicit completion evidence from one common-handler content block."""
    if not isinstance(block, dict) or block.get("type") != "text":
        raise ValueError("unsupported participant tool result")
    payload = json.loads(block["text"])
    if not isinstance(payload, dict) or (
        "success" in payload and type(payload["success"]) is not bool
    ):
        raise ValueError("invalid native completion status")
    if payload.get("session_mode") == "raw" or payload.get("failure") == "timeout":
        raise ValueError("native completion is unknown")
    return payload.get("success") is False or payload.get("exit_code", 0) not in (
        0,
        None,
    )


class LilraeToolSession:
    """One invocation's native adapter; RAES owns all portable decisions.

    No raw arguments/results persist in the session. The commitment and opaque
    handle prevent local replay; only RAES can issue the dispatch grant.
    """

    def __init__(
        self,
        port: ParticipantInvocationToolActionPort,
        bindings: tuple[LilraeToolBinding, ...],
        cancellation: Cancellation,
    ) -> None:
        self._port = port
        self.bindings = tuple(deepcopy(item) for item in bindings)
        self.cancellation = cancellation
        if not self.bindings or any(
            item.execution_binding.participant_implementation_ref
            != port.participant_implementation_ref
            for item in self.bindings
        ):
            raise ValueError("participant tool implementation mismatch")
        self._lock = RLock()
        self._calls: dict[tuple[str, str], tuple[bytes, LilraeToolCall]] = {}
        self._closed = False

    def transport(self) -> LilraeToolTransport:
        """Build the carrier owned by this adapter for the injected session port."""
        return LilraeToolTransport(self)

    @property
    def invocation_action_instance_id(self) -> str:
        return self._port.invocation_action_instance_id

    def _live(self) -> bool:
        return (
            not self._closed
            and not self.cancellation.is_set()
            and not self._port.closed
        )

    def begin(
        self,
        server: str,
        tool: str,
        arguments: dict[str, object],
        call_id: str,
        *,
        configuration: Mapping[str, object] | None = None,
    ) -> LilraeToolCall:
        """Resolve exact arguments and consume authority before native effects."""
        try:
            detached, data = _detached_json(arguments)
            effective, _ = _detached_json(
                configuration if configuration is not None else {}
            )
            if not isinstance(effective, dict):
                raise ValueError("invalid native configuration")
            configuration_digest = canonical_json_digest(effective)
            if not isinstance(detached, dict) or not _IDENTIFIER.fullmatch(call_id):
                raise ValueError("invalid call")
            with self._lock:
                self._require_available(server, call_id)
                matches = [
                    item
                    for item in self.bindings
                    if item.server_id == server
                    and item.tool_name == tool
                    and item.configuration_digest == configuration_digest
                    and item.accepts_arguments(deepcopy(detached)) is True
                ]
                if len(matches) != 1:
                    raise ValueError("ambiguous or unknown semantics")
                return self._admit(matches[0], call_id, data)
        except Exception:
            raise AgentExecutionError(_REFUSED) from None

    def _require_available(self, server: str, call_id: str) -> None:
        """Reject replay, closed authority and exceeded budgets while locked."""
        if (
            not self._live()
            or (server, call_id) in self._calls
            or len(self._calls) >= MAX_TOOL_ACTIONS
            or sum(
                call.state.phase == Phase.DISPATCHED for _, call in self._calls.values()
            )
            >= MAX_CONCURRENT_TOOLS
        ):
            raise ValueError("call unavailable")

    def _admit(
        self, binding: LilraeToolBinding, call_id: str, data: bytes
    ) -> LilraeToolCall:
        port = self._port
        # Server identity is part of the port's call identity. Neither role nor
        # a user-supplied participant address can choose the invocation.
        identity = sha256((binding.server_id + "\0" + call_id).encode()).hexdigest()
        decision = port.admit(
            ParticipantToolActionRequest(
                tool_call_id=identity,
                invocation_action_instance_id=port.invocation_action_instance_id,
                participant_address=port.participant_address,
                episode_id=port.episode_id,
                participant_implementation_ref=port.participant_implementation_ref,
                tool_affordance_address=binding.tool_affordance_address,
                action_contract_address=binding.execution_binding.action_contract_address,
                observation_boundary_address=binding.observation_boundary_address,
                target_addresses=binding.execution_binding.target_addresses,
                execution_scope_ref=port.execution_scope_ref,
                execution_generation=port.execution_generation,
            )
        )
        if not decision.admitted or not decision.action_instance_id:
            raise AgentExecutionError(_REFUSED)
        call = LilraeToolCall(
            binding, decision.action_instance_id, advance(ActionState(), Event.ADMIT)
        )
        self._calls[(binding.server_id, call_id)] = (sha256(data).digest(), call)
        if not self._live() or not port.dispatch(call.action_id).accepted:
            if port.cancel(call.action_id).accepted:
                call.state = advance(call.state, Event.WITHHOLD)
            raise AgentExecutionError(_REFUSED)
        call.state = advance(call.state, Event.DISPATCH)
        return call

    def _owns(self, call: LilraeToolCall) -> bool:
        return any(item is call for _, item in self._calls.values())

    def complete(
        self, call: LilraeToolCall, result: Mapping[str, object]
    ) -> dict[str, object]:
        """Deliver redacted data only after RAES accepts a terminal outcome."""
        with self._lock:
            if not self._owns(call) or call.state.phase != Phase.DISPATCHED:
                raise AgentExecutionError(_REFUSED)
            try:
                if not self._live():
                    raise ValueError("session closed")
                detached, _ = _detached_json(result)
                if not isinstance(detached, dict):
                    raise ValueError("invalid result")
                failed = _result_failed(detached)
                safe = redact_mcp_result(
                    detached, call.binding.server_id, call.binding.tool_name
                )
                outcome = ParticipantActionResultModel(
                    status="failed" if failed else "succeeded",
                    failure_class="backend_error" if failed else None,
                    participant_address=self._port.participant_address,
                    episode_id=self._port.episode_id,
                    action_instance_id=call.action_id,
                    action_contract_address=call.binding.execution_binding.action_contract_address,
                    observation_point=self._port.observation_point,
                )
                if not self._port.complete(call.action_id, outcome).accepted:
                    raise ValueError("outcome refused")
                call.state = advance(call.state, Event.COMPLETE)
                call.state = advance(call.state, Event.DELIVER)
                return safe
            except Exception:
                self.unknown(call)
                raise AgentExecutionError(_UNKNOWN) from None

    def unknown(self, call: LilraeToolCall) -> None:
        """Retain uncertainty without converting it into successful cleanup."""
        with self._lock:
            if self._owns(call) and call.state.phase == Phase.DISPATCHED:
                # Even a refused/unavailable ledger must not cause native replay.
                # The enclosing RAES invocation also closes all unsettled grants.
                try:
                    self._port.report_unknown(call.action_id, "backend_error")
                except Exception:
                    # RAES closes unresolved dispatched grants when the outer
                    # invocation ends. Still drain the other local calls.
                    pass
                finally:
                    call.state = advance(call.state, Event.UNKNOWN)

    def invoke(
        self,
        server: str,
        tool: str,
        arguments: dict[str, object],
        call_id: str,
        native: Callable[[dict[str, object]], Mapping[str, object]],
        *,
        configuration: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        """In-process carrier for trusted controllers and native adapters."""
        try:
            detached, _ = _detached_json(arguments)
        except Exception:
            raise AgentExecutionError(_REFUSED) from None
        call = self.begin(server, tool, detached, call_id, configuration=configuration)
        try:
            return self.complete(call, native(detached))
        except Exception:
            self.unknown(call)
            raise AgentExecutionError(_UNKNOWN) from None

    def states(self) -> tuple[ActionState, ...]:
        """Value-only adapter states for runtime conformance checks."""
        with self._lock:
            return tuple(call.state for _, call in self._calls.values())

    def close(self) -> None:
        """Stop admission and account for every unfinished dispatched call."""
        with self._lock:
            self._closed = True
            for _, call in self._calls.values():
                self.unknown(call)
