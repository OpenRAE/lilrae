"""Values and ports shared by participant controllers and native adapters."""

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
import re
from threading import Event as Cancellation
from typing import Protocol
from raes_backend_protocols.capabilities import ParticipantExecutionBinding
from aptl.core.participant_tools.model import ActionState

MAX_TOOL_ACTIONS = 16
MAX_CONCURRENT_TOOLS = 4
MAX_TOOL_FRAME = 1024 * 1024
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


@dataclass(frozen=True)
class LilraeToolBinding:
    """Management-selected semantics for one validated native call.

    The matcher is trusted installation code. It receives a detached argument
    value, must be side-effect free, and cannot change the declared authority.
    The contract digest binds the complete compiled action spec at planning.
    """

    server_id: str
    tool_name: str
    tool_affordance_address: str
    observation_boundary_address: str
    action_contract_digest: str
    configuration_digest: str
    execution_binding: ParticipantExecutionBinding
    accepts_arguments: Callable[[dict[str, object]], bool] = field(
        repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if (
            not _IDENTIFIER.fullmatch(self.server_id)
            or not _IDENTIFIER.fullmatch(self.tool_name)
            or not self.tool_affordance_address.startswith(
                "participant.behavior-specification."
            )
            or not self.observation_boundary_address.startswith(
                "participant.observation-boundary."
            )
            or re.fullmatch(r"sha256:[a-f0-9]{64}", self.action_contract_digest) is None
            or re.fullmatch(r"sha256:[a-f0-9]{64}", self.configuration_digest) is None
            or self.execution_binding.max_retries != 0
            or not callable(self.accepts_arguments)
        ):
            raise ValueError("invalid participant tool binding")


@dataclass(eq=False)
class LilraeToolCall:
    """Opaque local call handle; never supplied by the MCP peer."""

    binding: LilraeToolBinding
    action_id: str
    state: ActionState = field(default_factory=ActionState)


class ToolCarrier(Protocol):
    """Already-owned local authority delivered to one controller."""

    session: ToolSession
    timeout: float

    def environment(self, server: str) -> dict[str, str]: ...


class ToolSession(Protocol):
    """An invocation's port, without exposing an adapter implementation."""

    bindings: tuple[LilraeToolBinding, ...]
    cancellation: Cancellation

    @property
    def invocation_action_instance_id(self) -> str: ...
    def begin(
        self,
        server: str,
        tool: str,
        arguments: dict[str, object],
        call_id: str,
        *,
        configuration: Mapping[str, object] | None = None,
    ) -> LilraeToolCall: ...
    def complete(
        self, call: LilraeToolCall, result: Mapping[str, object]
    ) -> dict[str, object]: ...
    def unknown(self, call: LilraeToolCall) -> None: ...
    def close(self) -> None: ...
    def transport(self) -> AbstractContextManager[ToolCarrier]: ...
