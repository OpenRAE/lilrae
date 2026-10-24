"""Fixed startup hook slots, capabilities and delegated runtime authority."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from aptl.backends._scenario_environment import ScenarioStartupProviderError


class StartupCapability(str, Enum):
    """Fixed optional lab mechanics an exact scenario adapter may request."""

    SSH = "ssh"
    HOST_TOOLS = "host_tools"
    MCP = "mcp"
    NATIVE_EVIDENCE = "native_evidence"
    PARTICIPANT_DESKTOP = "participant_desktop"


class StartupHook(str, Enum):
    """Fixed lifecycle hook slots an admitted adapter may implement."""

    STACK_ENVIRONMENT = "stack_environment"
    BEFORE_BACKEND_RETRY = "before_backend_retry"
    RESET = "reset"


class StartupPreparationPhase(str, Enum):
    """Core-owned ordered preparation slots available to an adapter."""

    ENVIRONMENT = "environment"
    PRE_START_CONFIGURATION = "pre_start_configuration"
    PRE_START_STORAGE = "pre_start_storage"
    PRE_START_TRUST = "pre_start_trust"
    PRE_START_SERVICE_TRUST = "pre_start_service_trust"
    PRE_START_ARTIFACTS = "pre_start_artifacts"
    POST_START_READINESS = "post_start_readiness"
    POST_START_CONFIGURATION = "post_start_configuration"


@dataclass(frozen=True)
class StartupHookContext:
    """Narrow runtime authority passed to a selected startup hook."""

    backend: object | None
    preparation_phase: StartupPreparationPhase | None = None
    operation: Callable[[], object] | None = field(
        default=None, repr=False, compare=False
    )
    project_dir: Path | None = None

    def run_operation(self) -> object:
        """Run the single core operation delegated for this fixed phase."""

        if self.operation is None:
            raise ScenarioStartupProviderError("provider-hook-operation-unavailable")
        return self.operation()
