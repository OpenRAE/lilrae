"""Build managed MCP entries using current-run service and endpoint authority."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

from pydantic import JsonValue

from aptl.core.mcp_policy import (
    SERVER_IDS,
    WorkbenchConfigurationError,
    profile_for,
    service_bindings,
)


def _bind_endpoints(
    server_id: str, environment: dict[str, JsonValue], ports: Mapping[str, str]
) -> None:
    # No endpoint from a previous run is an authority for this run.
    for variable in tuple(environment):
        if variable.startswith("APTL_HP_"):
            del environment[variable]
    for binding in service_bindings(server_id):
        if binding.environment is None:
            continue
        port = ports.get(binding.environment, "")
        if not port.isdecimal() or not 0 < int(port) <= 65535:
            raise WorkbenchConfigurationError(
                "selected MCP service endpoint is unavailable"
            )
        environment[binding.environment] = port


def _bind_credentials(
    server_id: str, environment: dict[str, JsonValue], credentials: Mapping[str, str]
) -> None:
    aliases = {
        alias
        for role in ("red", "blue")
        for server in profile_for(role, server_ids=(server_id,)).servers
        for alias in server.credential_aliases
    }
    for alias in aliases:
        if alias in credentials:
            environment[alias] = credentials[alias]
        if not environment.get(alias):
            raise WorkbenchConfigurationError("selected MCP credential is unavailable")
    environment["APTL_MCP_DISABLE_DOTENV"] = "1"


def select_run_configuration(
    current: dict[str, JsonValue],
    template: dict[str, JsonValue],
    server_ids: tuple[str, ...],
    port_environment: Mapping[str, str],
    credentials: Mapping[str, str],
) -> dict[str, JsonValue]:
    """Drop selected-out servers and replace selected endpoint bindings.

    Assemble before writing, so a missing endpoint cannot publish a partial
    config or reuse a previous run's port. Preserve unrelated operator entries.
    """
    if set(server_ids) - set(SERVER_IDS):
        raise WorkbenchConfigurationError("unknown run MCP server")
    result = deepcopy(current)
    servers = result.setdefault("mcpServers", {})
    source = template.get("mcpServers", {})
    if not isinstance(servers, dict) or not isinstance(source, dict):
        raise WorkbenchConfigurationError("invalid MCP server configuration")
    for name in SERVER_IDS:
        previous = servers.pop(name, None)
        if name not in server_ids:
            continue
        spec = deepcopy(previous if previous is not None else source.get(name))
        if not isinstance(spec, dict) or not isinstance(spec.get("env"), dict):
            raise WorkbenchConfigurationError(
                "selected MCP server configuration is unavailable"
            )
        _bind_endpoints(name, spec["env"], port_environment)
        _bind_credentials(name, spec["env"], credentials)
        servers[name] = spec
    return result
