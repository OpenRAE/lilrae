"""Bounded OpenCode JSON events reduced to text and allowlisted metadata."""

from dataclasses import dataclass, field
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
    """Retain only a bounded session identifier and reject mixed sessions."""
    if not isinstance(candidate, str) or not re.fullmatch(
        r"ses_[A-Za-z0-9]{1,128}", candidate
    ):
        return previous
    if previous is not None and previous != candidate:
        raise ValueError("mixed sessions")
    return candidate


def _usage(tokens: dict[str, object], name: str, previous: int | None) -> int | None:
    """Accumulate bounded integer usage without accepting bool or float values."""
    value = tokens.get(name)
    if value is None:
        return previous
    if type(value) is not int or not 0 <= value <= 10**12:
        raise ValueError("invalid usage")
    return (previous or 0) + value


def _cost(value: object, previous: float | None) -> float | None:
    """Accumulate finite bounded cost without coercing oversized integers."""
    if value is None:
        return previous
    if type(value) not in {int, float} or not 0 <= value <= 10**6:
        raise ValueError("invalid cost")
    return (previous or 0) + value


def _part(event: dict[str, object]) -> dict[str, object]:
    """Require the event part to be an object before interpreting its fields."""
    part = event["part"]
    if not isinstance(part, dict):
        raise ValueError("invalid event part")
    return part


@dataclass
class _ResponseState:
    """Private reducer state; only its allowlisted response leaves the parser."""

    texts: list[str] = field(default_factory=list)
    session: str | None = None
    inputs: int | None = None
    outputs: int | None = None
    cost: float | None = None
    finish: str | None = None

    def accept(self, event: object) -> None:
        """Validate one event before changing terminal or text state."""
        if not isinstance(event, dict):
            raise ValueError("invalid event")
        self.session = _session(event.get("sessionID"), self.session)
        kind = event.get("type")
        if kind not in {"text", "step_start", "step_finish", "tool_use", "reasoning"}:
            raise ValueError("unknown event")
        if self.finish is not None and self.finish != "tool-calls":
            raise ValueError("events after terminal result")
        if kind == "text":
            text = _part(event)["text"]
            if not isinstance(text, str):
                raise ValueError("invalid text")
            text.encode("utf-8")
            self.texts.append(text)
        elif kind == "step_finish":
            self.accept_finish(_part(event))

    def accept_finish(self, part: dict[str, object]) -> None:
        """Retain the original finish and any valid partial usage fields."""
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
        self.finish = reason
        tokens = part.get("tokens", {})
        if not isinstance(tokens, dict):
            raise ValueError("invalid usage")
        self.inputs = _usage(tokens, "input", self.inputs)
        self.outputs = _usage(tokens, "output", self.outputs)
        self.cost = _cost(part.get("cost"), self.cost)

    def response(self, valid: bool) -> OpenCodeResponse:
        """Freeze safe partial facts, requiring text and a successful final stop."""
        text = "\n".join(self.texts)
        return OpenCodeResponse(
            text=text,
            valid=valid and bool(text.strip()) and self.finish == "stop",
            partial_text_sha256=hashlib.sha256(text.encode()).hexdigest()
            if self.texts
            else None,
            session_id=self.session,
            input_tokens=self.inputs,
            output_tokens=self.outputs,
            cost=self.cost,
            finish_reason=self.finish,
        )


def parse_opencode_response(output: bytes) -> OpenCodeResponse:
    """Require a complete stop event; never expose uncontrolled provider errors."""
    state = _ResponseState()
    valid = True
    try:
        for line in output.splitlines():
            if line.strip():
                state.accept(loads_strict(line))
    except ValueError, KeyError, TypeError, AttributeError:
        valid = False
    return state.response(valid)


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
