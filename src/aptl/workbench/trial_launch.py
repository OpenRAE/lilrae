"""Build one managed OpenCode executor for each declared trial participant."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, ExitStack, contextmanager
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from raes import Scenario
from raes_contracts.contracts import ParticipantControlContextAssetModel

from aptl.core._credential_sources import AttachedServiceAccountSource, ProcessEnvironmentCredentialSource
from aptl.core.config import ExperimentSettings
from aptl.core.mcp_policy import ProfileId, WorkbenchConfigurationError, profile_for
from aptl.core.opencode import (
    SUPPORTED_OPENCODE_BUILD,
    OpenCodeBuild,
    OpenCodeInvocationEvidence,
    OpenRouterRoute,
    ParticipantRoute,
    VertexRoute,
)
from aptl.core.participant_requests import decode_context_asset
from aptl.core.trial_sdl import DeclaredParticipant
from aptl.utils.pathsafe import create_exclusive_nofollow
from aptl.utils.redaction import redact
from aptl.workbench.agent import InventoryProbe, probe_mcp_server
from aptl.workbench.lilrae_opencode import (
    LilraeOpenCodeExecutor,
    OpenCodeOptions,
    OpenCodeToolProfile,
)
from aptl.workbench.participant_source_binding import ProcessEnvironmentCredentialResolver
from aptl.workbench.process import CancellableProcessRunner

__all__ = [
    "AssetReader",
    "TrialLaunchSettings",
    "invocation_fields",
    "participant_prompt",
    "participant_tool_servers",
    "trial_executors",
]

AssetReader = Callable[[ParticipantControlContextAssetModel], bytes]
_OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1"
_MAX_INVOCATION_SECONDS = 3600.0
_PROJECT = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
_NOT_SERVICE_ACCOUNT_KEY = "the Vertex AI credential is not a service account key"


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
    inventory_probe: InventoryProbe = probe_mcp_server
    #: The approved OpenRouter gateway. ``OpenRouterRoute`` admits only the live
    #: URL or an explicit loopback fake provider for qualification.
    openrouter_endpoint: str = _OPENROUTER_ENDPOINT


def participant_prompt(
    scenario: Scenario, participant: DeclaredParticipant, read_asset: AssetReader
) -> str:
    """Join the participant's selected asset bytes after each checksum check."""
    parts = []
    for key in participant.context_assets:
        asset = scenario.control_context_assets.get(key)
        if asset is None:
            raise ValueError(f"trial participant {participant.address} names a missing prompt")
        parts.append(decode_context_asset(asset, read_asset(asset)))
    return "".join(parts)


def participant_tool_servers(role: str, server_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Return the role's MCP servers that this run selected."""
    try:
        return profile_for(role, server_ids=server_ids).server_ids
    except WorkbenchConfigurationError as exc:
        raise ValueError(f"trial participant role {role!r} has no tool profile") from exc


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
    run_id: str,
    deadline: datetime,
    settings: TrialLaunchSettings,
    read_asset: AssetReader,
    evidence_sink: Callable[[str, OpenCodeInvocationEvidence], None],
    transcript_sink: Callable[[str, Mapping[str, object]], None] | None = None,
) -> Iterator[Mapping[str, LilraeOpenCodeExecutor]]:
    """Yield one executor per participant address; remove credentials on exit."""
    resolver = ProcessEnvironmentCredentialResolver(settings.source_environment)
    with ExitStack() as stack:
        executors = {}
        for participant in participants:
            prompt = participant_prompt(scenario, participant, read_asset)
            route, environment = stack.enter_context(
                _provider(participant.model, settings, resolver, run_id)
            )
            tools = _tool_profile(participant, settings, stack)
            executor = LilraeOpenCodeExecutor(
                options=OpenCodeOptions(
                    executable=settings.executable,
                    work_root=settings.work_root,
                    environment=environment,
                    max_output_tokens=settings.max_output_tokens,
                    runner=settings.runner,
                    tools=tools,
                    build=settings.build,
                    route=route,
                    evidence_sink=_address_sink(evidence_sink, participant.address),
                    transcript_sink=_address_sink(transcript_sink, participant.address)
                    if transcript_sink is not None
                    else None,
                    deadline=deadline,
                    tool_governance="allowlist",
                ),
                model=participant.model,
                prompt=prompt,
                timeout_seconds=_timeout(deadline),
            )
            stack.callback(executor.close)
            executors[participant.address] = executor
        yield MappingProxyType(executors)


def _timeout(deadline: datetime) -> float:
    """Bound one invocation; the executor also stops at the trial deadline."""
    remaining = (deadline - datetime.now(deadline.tzinfo)).total_seconds()
    return max(1.0, min(_MAX_INVOCATION_SECONDS, remaining))


def _address_sink[T](sink: Callable[[str, T], None], address: str) -> Callable[[T], None]:
    """Bind one participant address to the shared evidence sink."""
    return lambda evidence: sink(address, evidence)


@contextmanager
def _openrouter(
    model: str,
    settings: TrialLaunchSettings,
    resolver: ProcessEnvironmentCredentialResolver,
    run_id: str,
) -> Iterator[tuple[ParticipantRoute, Mapping[str, str]]]:
    """Route one model through the approved OpenRouter serving provider."""
    provider = settings.experiment.participant_serving_providers.get(model)
    if provider is None:
        raise ValueError(f"model {model} has no approved serving provider")
    route = OpenRouterRoute(endpoint=settings.openrouter_endpoint, serving_provider=provider)
    source = settings.experiment.participant_credential_sources.source_for("opencode")
    if not isinstance(source, ProcessEnvironmentCredentialSource):
        raise ValueError("the OpenRouter credential source must be a process environment variable")
    credentials, _ = resolver.acquire(
        "opencode", run_id, source=source, delivery_alias="OPENROUTER_API_KEY"
    )
    try:
        yield route, credentials
    finally:
        credentials.clear()


@contextmanager
def _vertex(
    model: str,
    settings: TrialLaunchSettings,
    resolver: ProcessEnvironmentCredentialResolver,
    run_id: str,
) -> Iterator[tuple[ParticipantRoute, Mapping[str, str]]]:
    """Give one Vertex AI participant a private key file, or the host's attached account."""
    source = settings.experiment.participant_credential_sources.source_for("vertex")
    if isinstance(source, AttachedServiceAccountSource):
        # Tokens come from the metadata server; no key exists to deliver or remove.
        yield VertexRoute(source.project), {"GOOGLE_CLOUD_PROJECT": source.project}
        return
    credentials, _ = resolver.acquire("vertex", run_id, source=source, delivery_alias="key")
    directory = Path(tempfile.mkdtemp(prefix="lilrae-vertex-", dir=settings.work_root))
    try:
        project = _key_project(credentials["key"])
        key = directory / "credentials.json"
        create_exclusive_nofollow(directory, key.name, credentials["key"].encode())
        os.chmod(key, 0o600)
        yield VertexRoute(project), {
            "GOOGLE_APPLICATION_CREDENTIALS": str(key),
            "GOOGLE_CLOUD_PROJECT": project,
            "METADATA_SERVER_DETECTION": "none",
        }
    finally:
        credentials.clear()
        shutil.rmtree(directory, ignore_errors=True)


def _key_project(key: str) -> str:
    """Read the service account project without echoing key content."""
    try:
        document = json.loads(key)
    except json.JSONDecodeError:
        raise ValueError(_NOT_SERVICE_ACCOUNT_KEY) from None
    if not isinstance(document, dict):
        raise ValueError(_NOT_SERVICE_ACCOUNT_KEY)
    project = document.get("project_id")
    if (
        document.get("type") != "service_account"
        or not isinstance(project, str)
        or not _PROJECT.fullmatch(project)
    ):
        raise ValueError(_NOT_SERVICE_ACCOUNT_KEY)
    return project


_PROVIDERS = {"openrouter/": _openrouter, "google-vertex/": _vertex}


def _provider(
    model: str,
    settings: TrialLaunchSettings,
    resolver: ProcessEnvironmentCredentialResolver,
    run_id: str,
) -> AbstractContextManager[tuple[ParticipantRoute, Mapping[str, str]]]:
    """Select the model's gateway by its provider prefix."""
    for prefix, launcher in _PROVIDERS.items():
        if model.startswith(prefix):
            return launcher(model, settings, resolver, run_id)
    raise ValueError(f"model {model} has no supported provider")


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
    servers = {name: _server_entry(document["mcpServers"][name], settings) for name in selected}
    directory = Path(tempfile.mkdtemp(prefix="lilrae-tools-", dir=settings.work_root))
    stack.callback(shutil.rmtree, directory, True)
    path = directory / "mcp.json"
    create_exclusive_nofollow(directory, path.name, json.dumps({"mcpServers": servers}).encode())
    os.chmod(path, 0o600)
    return OpenCodeToolProfile(
        profile=ProfileId(participant.role),
        config=path,
        inventory_probe=settings.inventory_probe,
        server_ids=selected,
    )


def _server_entry(entry: Mapping[str, object], settings: TrialLaunchSettings) -> dict[str, object]:
    """Resolve the run's MCP entry into the executor's strict absolute shape."""
    command = shutil.which(str(entry["command"]))
    if command is None:
        raise ValueError("a selected MCP server command is unavailable")
    base = settings.mcp_config.parent if settings.mcp_config is not None else Path.cwd()
    args = [_absolute_argument(base, str(arg)) for arg in entry.get("args", [])]
    return {
        "command": str(Path(command).resolve()),
        "args": args,
        "env": {str(key): str(value) for key, value in dict(entry.get("env", {})).items()},
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
