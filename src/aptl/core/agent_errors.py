"""Shared failure contract for bounded participant execution."""

from enum import StrEnum


class AgentExecutionError(RuntimeError):
    """The installed agent or one of its selected MCP servers failed safely."""


class BoundedStopReason(StrEnum):
    """Why the bounded process runner stopped an invocation early."""

    TIMEOUT = "agent request exceeded the configured timeout"
    CANCELLED = "agent request was cancelled"
    OVERFLOW = "agent output exceeded the configured limit"
    RESIDUE = "agent process cleanup left residual processes"
