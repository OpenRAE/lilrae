"""Bounded installed-agent result parsing and stable provider error classification."""

import json
from collections.abc import Mapping
from aptl.workbench.process import AgentExecutionError


def parse_claude_result(stdout: bytes) -> str:
    """Parse the installed agent's strict JSON result envelope."""
    try:
        payload = json.loads(stdout.decode("utf-8"))
        result = payload["result"]
        if (
            payload.get("type") != "result"
            or payload.get("is_error") is not False
            or not isinstance(result, str)
            or not result
        ):
            raise ValueError
        return result
    except (KeyError, ValueError) as exc:
        raise AgentExecutionError("agent returned an invalid result") from exc


def parse_codex_result(stdout: bytes) -> str:
    """Return the last completed agent message from Codex JSONL."""

    final_message: str | None = None
    try:
        for raw_line in stdout.decode("utf-8").splitlines():
            payload = json.loads(raw_line)
            item = payload.get("item")
            if (
                payload.get("type") == "item.completed"
                and isinstance(item, Mapping)
                and item.get("type") == "agent_message"
                and isinstance(item.get("text"), str)
                and item["text"]
            ):
                final_message = item["text"]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AgentExecutionError("agent returned an invalid result") from exc
    if final_message is None:
        raise AgentExecutionError("agent returned an invalid result")
    return final_message


def classify_codex_failure(stdout: bytes) -> str:
    """Map known hostile provider failures to stable, secret-free diagnostics."""

    try:
        events = [
            json.loads(raw_line)
            for raw_line in stdout.decode("utf-8").splitlines()
            if raw_line
        ]
    except UnicodeDecodeError, json.JSONDecodeError:
        return "agent request failed"
    messages: list[str] = []
    for event in events:
        if not isinstance(event, Mapping):
            continue
        if isinstance(event.get("message"), str):
            messages.append(event["message"])
        item = event.get("item")
        if isinstance(item, Mapping) and isinstance(item.get("message"), str):
            messages.append(item["message"])
    if any(
        "does not have access to model" in message.lower()
        or "model_not_found" in message.lower()
        or "model not found" in message.lower()
        for message in messages
    ):
        return "agent model is unavailable"
    return "agent request failed"
