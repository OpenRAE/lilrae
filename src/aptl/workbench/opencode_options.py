"""Installed OpenCode launch inputs, separate from sealed participant selection."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aptl.core.evidence.participant_capture import ParticipantCaptureArchive
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
import sys

from aptl.core.opencode import (
    OpenCodeBuild,
    OpenCodeInvocationEvidence,
    OpenCodeTrialScope,
    OpenRouterRoute,
    SUPPORTED_OPENCODE_BUILD,
)
from aptl.core.participant_requests.request import ParticipantRequest
from aptl.core.participant_requests.binding import ParticipantRequestBinding
from aptl.workbench.agent import InventoryProbe, probe_mcp_server
from aptl.workbench.process import CancellableProcessRunner
from aptl.workbench.profiles import ProfileId


def utc_now() -> datetime:
    """Read the UTC apparatus clock, with no local-time ambiguity."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class OpenCodeToolProfile:
    """An admitted MCP profile and the private inputs needed to verify it."""

    profile: ProfileId
    config: Path
    credentials: Mapping[str, str] = field(default_factory=dict, repr=False)
    inventory_probe: InventoryProbe = probe_mcp_server


@dataclass(frozen=True)
class OpenCodeOptions:
    """Operator-owned launch settings, separate from participant configuration."""

    executable: Path
    work_root: Path
    environment: Mapping[str, str] = field(default_factory=dict, repr=False)
    max_output_bytes: int = 1_000_000
    max_output_tokens: int = 128
    runner: CancellableProcessRunner | None = None
    tools: OpenCodeToolProfile | None = None
    build: OpenCodeBuild = SUPPORTED_OPENCODE_BUILD
    route: OpenRouterRoute | None = None
    evidence_sink: Callable[[OpenCodeInvocationEvidence], None] | None = None
    request: ParticipantRequest | None = None
    request_binding: ParticipantRequestBinding | None = None
    max_steps: int | None = None
    deadline: datetime | None = None
    clock: Callable[[], datetime] = utc_now
    trial_scope: OpenCodeTrialScope | None = None
    native_history_required: bool = False
    request_observation_required: bool = False
    capture: ParticipantCaptureArchive | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (
            self.native_history_required or self.request_observation_required
        ) and sys.platform != "linux":
            raise ValueError(
                "participant observation requires its qualified Linux platform"
            )
