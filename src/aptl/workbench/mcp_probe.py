"""Bounded MCP stdio inventory probing for installed participants."""

import asyncio
from collections.abc import Callable

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from aptl.workbench.process import AgentExecutionError

InventoryProbe = Callable[[str, str, list[str], dict[str, str]], tuple[str, ...]]


async def _probe(
    command: str, args: list[str], environment: dict[str, str]
) -> tuple[str, ...]:
    """Initialize the admitted stdio server and collect its tool names."""
    parameters = StdioServerParameters(command=command, args=args, env=environment)
    async with (
        stdio_client(parameters) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream, read_timeout_seconds=10.0) as session,
    ):
        await session.initialize()
        result = await session.list_tools()
        return tuple(tool.name for tool in result.tools)


def probe_mcp_server(
    server_id: str, command: str, args: list[str], environment: dict[str, str]
) -> tuple[str, ...]:
    """Perform a real MCP initialize and tools/list exchange over stdio."""
    try:
        return asyncio.run(_probe(command, args, environment))
    except Exception as exc:
        raise AgentExecutionError(
            f"MCP inventory probe failed for {server_id}"
        ) from exc
