"""Shared failure contract for bounded participant execution."""


class AgentExecutionError(RuntimeError):
    """The installed agent or one of its selected MCP servers failed safely."""
