"""Operator-owned MCP catalog and selection from admitted service declarations."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import Enum
import json
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, model_validator

from aptl.core.scenario_bundle import PackIdentity

if TYPE_CHECKING:
    from raes.scenario import Scenario


class WorkbenchConfigurationError(ValueError):
    """The requested MCP compartment cannot safely produce a configuration."""


class ProfileId(str, Enum):
    """Operator-admitted participant roles."""

    RED = "red"
    GUIDED_BLUE = "guided-blue"
    BLUE = "blue"


@dataclass(frozen=True)
class ServerProfile:
    """An operator-admitted artifact, credential aliases, and exact tools."""

    server_id: str
    artifact_ref: str
    credential_aliases: tuple[str, ...] = ()
    tool_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkbenchProfile:
    """An immutable launch compartment, not a client-side tool filter."""

    profile_id: ProfileId
    servers: tuple[ServerProfile, ...]
    bookmark_refs: tuple[str, ...]
    policy_version: str = "participant-workbench-profile/v1"
    runtime_environment: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = ()

    @property
    def server_ids(self) -> tuple[str, ...]:
        """Return the selected server identities in operator order."""
        return tuple(server.server_id for server in self.servers)

    @property
    def credential_aliases(self) -> tuple[str, ...]:
        """Return only credential aliases required by selected servers."""
        return tuple(
            sorted({alias for s in self.servers for alias in s.credential_aliases})
        )


class _PolicyValue(BaseModel):
    """Strict immutable values read from operator-owned policy data."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ServiceBinding(_PolicyValue):
    """An exact declared node/service and its existing MCP port variable."""

    node: str
    port: int | None
    environment: str | None
    endpoint_node: str | None = None
    endpoint_port: int | None = None


class _Server(_PolicyValue):
    """One catalog server and the services needed to admit it."""

    server_id: str
    artifact_ref: str
    credential_aliases: tuple[str, ...]
    tool_names: tuple[str, ...]
    services: tuple[ServiceBinding, ...]

    def profile(self) -> ServerProfile:
        """Project the admitted launch contract without service-selection data."""
        return ServerProfile(
            self.server_id, self.artifact_ref, self.credential_aliases, self.tool_names
        )


class _Role(_PolicyValue):
    """Operator ceiling for a participant role and its browser references."""

    servers: tuple[str, ...]
    bookmarks: tuple[str, ...]


class _Catalog(_PolicyValue):
    """Shipped operator server definitions and role ceilings."""

    servers: dict[str, _Server]
    profiles: dict[ProfileId, _Role]


_CATALOG = _Catalog.model_validate_json(
    files("aptl.core").joinpath("participant_mcp_policy.json").read_text()
)
SERVER_IDS = tuple(_CATALOG.servers)


class McpPolicy(_PolicyValue):
    """Operator ceiling; scenario packs cannot supply this configuration."""

    allowed_servers: tuple[str, ...] = SERVER_IDS
    required_servers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_ceiling(self) -> McpPolicy:
        """Reject unknown servers and requirements outside the operator ceiling."""
        if (set(self.allowed_servers) | set(self.required_servers)) - set(
            SERVER_IDS
        ) or set(self.required_servers) - set(self.allowed_servers):
            raise ValueError("invalid operator MCP policy")
        return self


class McpRunAdmission(_PolicyValue):
    """Private projection of an exact admission for later guest enrollment."""

    run_id: str
    pack: PackIdentity
    server_ids: tuple[str, ...]
    container_aliases: tuple[tuple[str, ...], ...]


def profile_for(
    profile: ProfileId | str, *, server_ids: Collection[str] | None = None
) -> WorkbenchProfile:
    """Intersect an active selection with its operator-owned role ceiling.

    Omitting server_ids returns the catalog for packaging and policy inspection.
    Execution callers supply the admitted run's selection, including an empty one.
    """
    try:
        role_id = ProfileId(profile)
    except ValueError as exc:
        raise WorkbenchConfigurationError("unknown participant profile") from exc
    role = _CATALOG.profiles[role_id]
    admitted = set(SERVER_IDS if server_ids is None else server_ids)
    if admitted - set(SERVER_IDS):
        raise WorkbenchConfigurationError("unknown MCP server in selection")
    return WorkbenchProfile(
        role_id,
        tuple(
            _CATALOG.servers[name].profile()
            for name in role.servers
            if name in admitted
        ),
        role.bookmarks,
    )


def select_scenario_servers(scenario: Scenario, policy: McpPolicy) -> tuple[str, ...]:
    """Select only services from the exact admitted scenario before any mutation."""
    allowed, required = set(policy.allowed_servers), set(policy.required_servers)
    if (allowed | required) - set(SERVER_IDS) or required - allowed:
        raise WorkbenchConfigurationError("invalid operator MCP policy")
    selected = tuple(
        name
        for name, server in _CATALOG.servers.items()
        if name in allowed
        and all(
            binding.node in scenario.nodes
            and (
                binding.port is None
                or any(
                    service.port == binding.port and service.protocol == "tcp"
                    for service in scenario.nodes[binding.node].services
                )
            )
            for binding in server.services
        )
    )
    if required - set(selected):
        raise WorkbenchConfigurationError("required MCP server has no declared service")
    return selected


def service_bindings(server_id: str) -> tuple[ServiceBinding, ...]:
    """Return only operator-declared service and endpoint bindings."""
    return _CATALOG.servers[server_id].services


def configured_server_ids(project_dir: Path, run_id: str) -> tuple[str, ...]:
    """Read the current run's selection; a missing config grants no servers."""
    path = project_dir / ".mcp.json"
    if not path.exists():
        return ()
    document = json.loads(path.read_text())
    servers = document.get("mcpServers")
    if not isinstance(servers, dict):
        raise WorkbenchConfigurationError("invalid run MCP configuration")
    selected = tuple(name for name in SERVER_IDS if name in servers)
    if any(
        servers[name].get("env", {}).get("APTL_MCP_ADMITTED_RUN_ID") != run_id
        for name in selected
    ):
        raise WorkbenchConfigurationError("MCP configuration belongs to another run")
    return selected


def configured_runtime_environment(
    project_dir: Path, run_id: str
) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    """Copy only selected, non-secret endpoint bindings into an agent launch."""
    selected = configured_server_ids(project_dir, run_id)
    if not selected:
        return ()
    document = json.loads((project_dir / ".mcp.json").read_text())
    return tuple(
        (
            name,
            tuple(
                (
                    binding.environment,
                    document["mcpServers"][name]["env"][binding.environment],
                )
                for binding in service_bindings(name)
                if binding.environment is not None
            ),
        )
        for name in selected
    )
