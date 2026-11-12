"""Build one managed OpenCode executor for each declared trial participant."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from types import MappingProxyType

from raes import Scenario
from raes_contracts.contracts import ParticipantControlContextAssetModel

from aptl.core.config import (
    ExperimentSettings,
)
from aptl.core.mcp_policy import ProfileId, WorkbenchConfigurationError, profile_for
from aptl.core.opencode import (
    OpenCodeTrialScope,
    SUPPORTED_OPENCODE_BUILD,
    OpenCodeBuild,
    OpenCodeInvocationEvidence,
)
from aptl.core.participant_requests import decode_context_asset
from aptl.core.trial_attempt import TrialAttempt
from aptl.core.trial_sdl import DeclaredParticipant
from aptl.utils.pathsafe import create_exclusive_nofollow
from aptl.utils.redaction import redact
from aptl.workbench.agent import InventoryProbe, probe_mcp_server
from aptl.workbench.lilrae_opencode import (
    LilraeOpenCodeExecutor,
    OpenCodeOptions,
    OpenCodeToolProfile,
)
from aptl.workbench.process import CancellableProcessRunner

__all__ = [
    "AssetReader",
    "TrialLaunchSettings",
    "TrialSinks",
    "invocation_fields",
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
    build: OpenCodeBuild = SUPPORTED_OPENCODE_BUILD
    runner: CancellableProcessRunner | None = None
    inventory_probe: InventoryProbe = probe_mcp_server


@dataclass(frozen=True)
class TrialSinks:
    """Receivers of each participant's invocation evidence and native session export."""

    evidence: Callable[[str, OpenCodeInvocationEvidence], None]
    transcript: Callable[[str, Mapping[str, object]], None] | None = None


def participant_prompt(
    scenario: Scenario, participant: DeclaredParticipant, read_asset: AssetReader
) -> str:
    """Join the participant's selected asset bytes after each checksum check."""
    parts = []
    for key in participant.context_assets:
        asset = scenario.control_context_assets.get(key)
        if asset is None:
            raise ValueError(
                f"trial participant {participant.address} names a missing prompt"
            )
        parts.append(decode_context_asset(asset, read_asset(asset)))
    return "".join(parts)


def participant_tool_servers(role: str, server_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Return the role's MCP servers that this run selected."""
    try:
        return profile_for(role, server_ids=server_ids).server_ids
    except WorkbenchConfigurationError as exc:
        raise ValueError(
            f"trial participant role {role!r} has no tool profile"
        ) from exc


def invocation_fields(evidence: OpenCodeInvocationEvidence) -> dict[str, object]:
    """Return the allowlisted invocation facts as JSON values the run store accepts.

    The shared secret policy classifies identifiers such as the session ID; the
    record keeps the redacted form that the run store would persist.
    """
    return redact(json.loads(json.dumps(_plain(evidence), default=str)))


@contextmanager
def trial_executors(
    scenario: Scenario,
    participants: tuple[DeclaredParticipant, ...],
    *,
    attempt: TrialAttempt,
    bindings: Mapping[str, object],
    settings: TrialLaunchSettings,
    read_asset: AssetReader,
    sinks: TrialSinks,
) -> Iterator[Mapping[str, LilraeOpenCodeExecutor]]:
    """Use the existing managed native adapter for each sealed participant request."""
    from aptl.workbench.opencode_bootstrap import (
        OpenCodeParticipantRequest,
        managed_opencode_executor,
    )
    from aptl.workbench.trial_participants import participant_route

    if attempt.unit is None:
        raise ValueError("native trial execution requires its admitted plan entry")
    with ExitStack() as stack:
        executors = {}
        for participant in participants:
            binding = bindings[participant.address]
            pending = binding.executor
            request = pending.request
            if (
                request is None
                or pending.request_binding is None
                or request.profile.assistant_turn_limit is None
            ):
                raise ValueError(
                    "the installed native participant has no sealed request or turn bound"
                )
            if (
                participant_prompt(scenario, participant, read_asset) != request.prompt
                or participant.model != request.profile.model
            ):
                raise ValueError(
                    "the trial prompt or model differs from its admitted request"
                )
            source = settings.experiment.participant_credential_sources.source_for(
                "vertex" if request.profile.gateway == "google-vertex" else "opencode"
            )
            options = OpenCodeOptions(
                executable=settings.executable,
                work_root=settings.work_root,
                max_output_tokens=request.profile.output_limit.value,
                runner=settings.runner,
                tools=_tool_profile(participant, settings, stack),
                build=settings.build,
                route=participant_route(request.profile, source),
                evidence_sink=_address_sink(sinks.evidence, participant.address),
                transcript_sink=_address_sink(sinks.transcript, participant.address)
                if sinks.transcript
                else None,
                deadline=attempt.deadline,
                request=request,
                request_binding=pending.request_binding,
                max_steps=request.profile.assistant_turn_limit.value,
                trial_scope=OpenCodeTrialScope(
                    attempt.run_id, attempt.attempt_id, attempt.unit.plan_entry_id
                ),
                native_history_required=True,
                request_observation_required=True,
            )
            executor, _ = stack.enter_context(
                managed_opencode_executor(
                    options=options,
                    request=OpenCodeParticipantRequest(
                        pending.configuration_result,
                        binding.implementation_manifest,
                        request.prompt,
                        request.prompt_ref,
                        frozenset({request.profile.model}),
                    ),
                    run_id=attempt.run_id,
                    credential_source=source,
                    source_environment=settings.source_environment,
                    timeout_seconds=binding.execution_binding.timeout_seconds,
                )
            )
            executors[participant.address] = executor
        yield MappingProxyType(executors)


def _address_sink[T](
    sink: Callable[[str, T], None], address: str
) -> Callable[[T], None]:
    """Bind one participant address to a trial-wide sink."""
    return lambda evidence: sink(address, evidence)


def _tool_profile(
    participant: DeclaredParticipant, settings: TrialLaunchSettings, stack: ExitStack
) -> OpenCodeToolProfile | None:
    """Write a private MCP config with only the run-selected servers of the role."""
    if settings.mcp_config is None:
        return None
    selected = participant_tool_servers(participant.role, settings.server_ids)
    if not selected:
        return None
    document = json.loads(settings.mcp_config.read_text(encoding="utf-8"))
    servers = {
        name: _server_entry(document["mcpServers"][name], settings) for name in selected
    }
    directory = Path(tempfile.mkdtemp(prefix="lilrae-tools-", dir=settings.work_root))
    stack.callback(shutil.rmtree, directory, True)
    path = directory / "mcp.json"
    create_exclusive_nofollow(
        directory, path.name, json.dumps({"mcpServers": servers}).encode()
    )
    os.chmod(path, 0o600)
    return OpenCodeToolProfile(
        profile=ProfileId(participant.role),
        config=path,
        inventory_probe=settings.inventory_probe,
        server_ids=selected,
    )


def _server_entry(
    entry: Mapping[str, object], settings: TrialLaunchSettings
) -> dict[str, object]:
    """Resolve the run's MCP entry into the executor's strict absolute shape."""
    command = shutil.which(str(entry["command"]))
    if command is None:
        raise ValueError("a selected MCP server command is unavailable")
    base = settings.mcp_config.parent if settings.mcp_config is not None else Path.cwd()
    args = [_absolute_argument(base, str(arg)) for arg in entry.get("args", [])]
    return {
        "command": str(Path(command).resolve()),
        "args": args,
        "env": {
            str(key): str(value) for key, value in dict(entry.get("env", {})).items()
        },
    }


def _absolute_argument(base: Path, argument: str) -> str:
    """Anchor a project-relative script path; keep flags and other values."""
    if argument.startswith("-") or Path(argument).is_absolute():
        return argument
    candidate = base / argument
    return str(candidate.resolve()) if candidate.exists() else argument


def _plain(value: object) -> object:
    """Convert nested dataclasses and tuples to plain JSON-shaped values."""
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _plain(item) for key, item in asdict(value).items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value
