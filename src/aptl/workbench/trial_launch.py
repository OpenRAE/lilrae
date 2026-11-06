"""Build one managed OpenCode executor for each declared trial participant."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from raes import Scenario
from raes_contracts.contracts import ParticipantControlContextAssetModel

from aptl.core.config import ExperimentSettings
from aptl.core.opencode import (
    SUPPORTED_OPENCODE_BUILD,
    OpenCodeBuild,
    OpenCodeInvocationEvidence,
)
from aptl.core.trial_sdl import DeclaredParticipant
from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor
from aptl.workbench.process import CancellableProcessRunner

__all__ = [
    "AssetReader",
    "TrialLaunchSettings",
    "participant_prompt",
    "participant_tool_servers",
    "trial_executors",
]

AssetReader = Callable[[ParticipantControlContextAssetModel], bytes]


@dataclass(frozen=True)
class TrialLaunchSettings:
    """Operator-owned launch inputs for every participant of one trial."""

    executable: Path
    work_root: Path
    experiment: ExperimentSettings
    source_environment: Mapping[str, str] = field(repr=False)
    mcp_config: Path | None = None
    server_ids: tuple[str, ...] = ()
    max_output_tokens: int = 32768
    build: OpenCodeBuild = SUPPORTED_OPENCODE_BUILD
    runner: CancellableProcessRunner | None = None


def participant_prompt(
    scenario: Scenario, participant: DeclaredParticipant, read_asset: AssetReader
) -> str:
    """Join the participant's selected asset bytes after each checksum check."""
    raise ValueError("trial participant prompts are not supported")


def participant_tool_servers(role: str, server_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Return the role's MCP servers that this run selected."""
    raise ValueError("trial participant tools are not supported")


@contextmanager
def trial_executors(
    scenario: Scenario,
    participants: tuple[DeclaredParticipant, ...],
    *,
    run_id: str,
    deadline: datetime,
    settings: TrialLaunchSettings,
    read_asset: AssetReader,
    evidence_sink: Callable[[str, OpenCodeInvocationEvidence], None],
) -> Iterator[Mapping[str, LilraeOpenCodeExecutor]]:
    """Yield one executor per participant address; remove credentials on exit."""
    raise ValueError("trial participant launch is not supported")
    yield {}
