"""Installed participant bindings, independent of runtime reservations."""

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event
from raes_backend_protocols.capabilities import ParticipantExecutionBinding
from raes_contracts.contracts import (
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
)
from raes_contracts.satisfiability import canonical_contract_digest
from raes_contracts.participant_configuration import (
    validate_participant_configuration_selection,
)
from aptl.core.participant_tools.contracts import LilraeToolBinding

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
    tool_bindings: tuple[LilraeToolBinding, ...] = ()

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
        self._validate_executor()
        self._validate_tool_executor()

    def _validate_tool_executor(self) -> None:
        """Match tool authority to the executor and its installed inventory."""
        if self.tool_bindings and (
            not callable(getattr(self.executor, "invoke_with_tools", None))
            or any(
                tool.execution_binding.participant_implementation_ref
                != self.implementation_selection.manifest_ref
                for tool in self.tool_bindings
            )
        ):
            raise ValueError("tool bindings require a matching tool-enabled executor")
        inventory = getattr(self.executor, "tool_inventory", None)
        if inventory is not None and inventory != frozenset(
            (tool.server_id, tool.tool_name) for tool in self.tool_bindings
        ):
            raise ValueError(
                "installed tool bindings differ from the executor inventory"
            )

    def _validate_executor(self) -> None:
        """Require the executor's configuration and deadline to match admission."""
        configuration = getattr(self.executor, "configuration_result", None)
        if (
            self.implementation_manifest.configuration_registry is not None
            and configuration is None
        ):
            raise ValueError(
                "participant configuration result is required by its manifest"
            )
        if configuration is not None:
            validate_participant_configuration_selection(
                self.implementation_selection, configuration
            )
        if (
            hasattr(self.executor, "timeout_seconds")
            and self.executor.timeout_seconds > self.execution_binding.timeout_seconds
        ):
            raise ValueError("participant executor exceeds the admitted timeout")
