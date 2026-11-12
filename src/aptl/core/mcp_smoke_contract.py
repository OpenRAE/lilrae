"""Public values for adapter-owned participant MCP smoke plans (ADR-067).

An ``aptl.participant_mcp_smoke_plans`` entry point loads either a static tuple
of :class:`McpSmokeOperation` values or a :class:`McpSmokeProvider`. A provider
declares its possible checks for discovery and resolves executable operations
from one immutable :class:`McpSmokeContext` built from the admitted run. The
context carries identities, grants, and admitted node facts only; it carries no
credential, environment, configuration, path, or runtime handle.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from aptl.core.scenario_bundle import PackIdentity

SMOKE_PROVIDER_API_VERSION = "1"


class ParticipantMcpSmokeError(ValueError):
    """The admitted profile cannot run its exact MCP smoke surface."""


class ParticipantSmokeTargetError(ParticipantMcpSmokeError):
    """A provider asked for a target that the admitted run does not supply."""

    def __init__(self) -> None:
        super().__init__("participant smoke target is not admitted")


@dataclass(frozen=True)
class McpSmokeOperation:
    """One plugin-owned readiness check bound to a released MCP tool call."""

    check_id: str
    server_id: str
    tool_name: str
    arguments: Mapping[str, object]
    validates: Callable[[Mapping[str, object]], bool]


@dataclass(frozen=True)
class McpSmokeCheck:
    """One check a plan may emit, declared without arguments or a validator."""

    check_id: str
    server_id: str
    tool_name: str


@dataclass(frozen=True)
class McpToolGrant:
    """One admitted MCP server and the exact tools its role ceiling grants."""

    server_id: str
    tool_names: tuple[str, ...]


@dataclass(frozen=True)
class AdmittedServicePort:
    """One service port that an admitted SDL node declares."""

    name: str
    port: int
    protocol: str = "tcp"


@dataclass(frozen=True)
class AdmittedAddress:
    """One static address that the admitted realization assigns on a network."""

    network: str
    address: str


@dataclass(frozen=True)
class AdmittedNode:
    """One realized SDL node of the admitted run and its declared endpoints."""

    name: str
    services: tuple[AdmittedServicePort, ...] = ()
    addresses: tuple[AdmittedAddress, ...] = ()


@dataclass(frozen=True)
class McpSmokeContext:
    """Immutable, non-secret admitted inputs for one provider resolution."""

    extension_api_version: str
    profile_id: str
    scenario_id: str
    pack: PackIdentity | None
    nodes: tuple[AdmittedNode, ...]
    grants: tuple[McpToolGrant, ...]
    checks: tuple[McpSmokeCheck, ...]

    def node(self, name: str) -> AdmittedNode | None:
        """Return the admitted node with this SDL name, or ``None``."""

        return next((node for node in self.nodes if node.name == name), None)

    def address(self, node: str, network: str) -> str:
        """Return the one admitted address of ``node`` on ``network``."""

        admitted = self.node(node)
        addresses = (
            ()
            if admitted is None
            else tuple(
                item.address for item in admitted.addresses if item.network == network
            )
        )
        if len(addresses) != 1:
            raise ParticipantSmokeTargetError()
        return addresses[0]


class McpSmokeProvider(Protocol):
    """Installed provider contract; installation grants normal Python authority."""

    extension_api_version: str
    checks: tuple[McpSmokeCheck, ...]

    def resolve(self, context: McpSmokeContext) -> tuple[McpSmokeOperation, ...]:
        """Return operations for the admitted inputs without side effects."""
        ...


__all__ = [
    "SMOKE_PROVIDER_API_VERSION",
    "AdmittedAddress",
    "AdmittedNode",
    "AdmittedServicePort",
    "McpSmokeCheck",
    "McpSmokeContext",
    "McpSmokeOperation",
    "McpSmokeProvider",
    "McpToolGrant",
    "ParticipantMcpSmokeError",
    "ParticipantSmokeTargetError",
]
