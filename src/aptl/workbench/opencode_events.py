"""Bounded OpenCode JSON events reduced to text and allowlisted metadata."""

from dataclasses import dataclass
import hashlib
import re

from aptl.utils.strict_json import loads_strict
from aptl.workbench.process import (
    AgentExecutionError,
    BoundedProcessError,
    ProcessResult,
)


@dataclass(frozen=True)
class OpenCodeResponse:
    """Safe partial observation, even when the terminal response is invalid."""

    text: str
    valid: bool
    partial_text_sha256: str | None
    session_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost: float | None
    finish_reason: str | None


def _session(candidate: object, previous: str | None) -> str | None:
    if not isinstance(candidate, str) or not re.fullmatch(
        r"ses_[A-Za-z0-9]{1,128}", candidate
    ):
        return previous
    if previous is not None and previous != candidate:
        raise ValueError("mixed sessions")
    return candidate


def _usage(tokens: dict, name: str, previous: int | None) -> int | None:
    value = tokens.get(name)
    if value is None:
        return previous
    if type(value) is not int or not 0 <= value <= 10**12:
        raise ValueError("invalid usage")
    return (previous or 0) + value


def parse_opencode_response(output: bytes) -> OpenCodeResponse:
    """Require a complete stop event; never expose uncontrolled provider errors."""
    texts: list[str] = []
    session = None
    inputs = outputs = None
    cost = None
    finish = None
    valid = True
    try:
        for line in output.splitlines():
            if not line.strip():
                continue
            event = loads_strict(line)
            if not isinstance(event, dict):
                raise ValueError("invalid event")
            session = _session(event.get("sessionID"), session)
            kind = event.get("type")
            if kind not in {
                "text",
                "step_start",
                "step_finish",
                "tool_use",
                "reasoning",
            }:
                raise ValueError("unknown event")
            if finish is not None and finish != "tool-calls":
                raise ValueError("events after terminal result")
            if kind == "text":
                text = event["part"]["text"]
                if not isinstance(text, str):
                    raise ValueError("invalid text")
                text.encode("utf-8")
                texts.append(text)
            elif kind == "step_finish":
                part = event["part"]
                reason = part["reason"]
                if reason not in {
                    "stop",
                    "tool-calls",
                    "length",
                    "content-filter",
                    "error",
                    "other",
                    "unknown",
                }:
                    raise ValueError("invalid finish reason")
                finish = reason
                tokens = part.get("tokens", {})
                inputs = _usage(tokens, "input", inputs)
                outputs = _usage(tokens, "output", outputs)
                value = part.get("cost")
                if value is not None:
                    if type(value) not in {int, float} or not 0 <= value <= 10**6:
                        raise ValueError("invalid cost")
                    cost = (cost or 0) + value
    except ValueError, KeyError, TypeError, AttributeError:
        valid = False
    text = "\n".join(texts)
    return OpenCodeResponse(
        text=text,
        valid=valid and bool(text.strip()) and finish == "stop",
        partial_text_sha256=hashlib.sha256(text.encode()).hexdigest()
        if texts
        else None,
        session_id=session,
        input_tokens=inputs,
        output_tokens=outputs,
        cost=cost,
        finish_reason=finish,
    )


def _supervised_result_text(result: ProcessResult) -> str:
    """Keep cleanup proof when a terminated harness cannot supply usable output."""
    try:
        if result.returncode != 0:
            raise AgentExecutionError("participant harness exited unsuccessfully")
        return _terminal_text(result.stdout)
    except AgentExecutionError as exc:
        if result.cleanup is None:
            raise
        raise BoundedProcessError(
            str(exc),
            cleanup=result.cleanup,
            stdout_bytes=len(result.stdout),
            stderr_bytes=len(result.stderr),
            stdout_sha256=hashlib.sha256(result.stdout).hexdigest(),
        ) from None


def _terminal_text(output: bytes) -> str:
    """Parse bounded JSON events without exposing malformed provider output."""
    response = parse_opencode_response(output)
    if not response.valid:
        raise AgentExecutionError("participant harness output is invalid")
    return response.text
