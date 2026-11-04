"""Redact logical response text before retaining fragmented transport events."""

from collections.abc import Iterator
from copy import deepcopy
import json
from aptl.utils.redaction import redact_granted_secrets
from aptl.utils.strict_json import loads_strict

_METADATA = {
    "id",
    "model",
    "provider",
    "usage",
    "object",
    "created",
    "system_fingerprint",
    "service_tier",
}
type ContentPath = tuple[str, ...]
type StreamKey = tuple[str, object, ContentPath]
type Record = dict[str, object]


def _strings(
    value: object, path: ContentPath = (), depth: int = 0
) -> Iterator[tuple[ContentPath, str]]:
    """Yield logical response string paths within a fixed nesting bound."""
    if depth >= 32:
        raise ValueError("response content nesting exceeded")
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _strings(child, (*path, key), depth + 1)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            position = child.get("index", index) if isinstance(child, dict) else index
            yield from _strings(child, (*path, str(position)), depth + 1)


def _choice_content(
    choice: Record, request: str, index: object, streams: dict[StreamKey, list[str]]
) -> bool:
    """Combine each content carrier independently and disclose unsupported nesting."""
    withheld = False
    for carrier in ("delta", "message", "text"):
        if carrier not in choice:
            continue
        try:
            leaves = list(_strings(choice[carrier], (carrier,)))
        except ValueError:
            withheld = True
            continue
        for path, text in leaves:
            streams.setdefault((request, index, path), []).append(text)
    return withheld


def _response_metadata(
    row: Record, streams: dict[StreamKey, list[str]], finished: set[tuple[str, object]]
) -> bool:
    """Retain frame metadata while moving content into logical response streams."""
    payload = loads_strict(row["json"])
    request = row["request_id"]
    metadata = {key: value for key, value in payload.items() if key in _METADATA}
    choices = []
    withheld = False
    for position, choice in enumerate(payload.get("choices", [])):
        index = choice.get("index", position)
        choices.append({"index": index, "finish_reason": choice.get("finish_reason")})
        if choice.get("finish_reason") or "message" in choice:
            finished.add((request, index))
        withheld |= _choice_content(choice, request, index, streams)
    if withheld:
        row["content_withheld_reason"] = "unsupported nesting"
    if choices:
        metadata["choices"] = choices
    row["json"] = json.dumps(metadata, separators=(",", ":"))
    return withheld


def _retain_content(
    streams: dict[StreamKey, list[str]],
    completed: set[str],
    finished: set[tuple[str, object]],
    last: dict[str, Record],
    secrets: tuple[str, ...],
) -> bool:
    """Redact complete logical responses and withhold every unfinished stream."""
    withheld = False
    for (request, index, path), pieces in streams.items():
        item: Record = {"choice_index": index, "path": list(path)}
        if request in completed and (request, index) in finished:
            item["value"] = redact_granted_secrets("".join(pieces), secrets)
        else:
            item["value"] = None
            item["withheld_reason"] = "incomplete streamed response"
            withheld = True
        last[request].setdefault("response_content", []).append(item)
    return withheld


def redact_response_records(
    records: list[Record], calls: list[Record], secrets: tuple[str, ...]
) -> tuple[list[Record], bool]:
    """Keep frame metadata and combine content before redaction; withhold incomplete text."""
    output: list[Record] = []
    streams: dict[StreamKey, list[str]] = {}
    last: dict[str, Record] = {}
    finished: set[tuple[str, object]] = set()
    completed = {call["request_id"] for call in calls if call["state"] == "completed"}
    withheld = False
    for original in records:
        row = dict(original)
        output.append(row)
        if row["kind"] == "response":
            last[row["request_id"]] = row
            withheld |= _response_metadata(row, streams, finished)
    withheld |= _retain_content(streams, completed, finished, last, secrets)
    return [redact_granted_secrets(row, secrets) for row in output], withheld


def _cli_text_event(event: Record, kind: str) -> bool:
    """Select only the requested text kind with a structured textual part."""
    return (
        event.get("type") == kind
        and isinstance(event.get("part"), dict)
        and isinstance(event["part"].get("text"), str)
    )


def redact_cli_content(
    events: list[Record], secrets: tuple[str, ...], *, complete: bool
) -> list[Record]:
    """Retain text once after combining same-kind CLI events, with original metadata."""
    output = deepcopy(events)
    for kind in ("text", "reasoning"):
        selected = [event for event in output if _cli_text_event(event, kind)]
        text = "".join(event["part"]["text"] for event in selected)
        for event in selected:
            event["part"]["text"] = ""
        if selected:
            selected[-1]["part"]["text"] = (
                redact_granted_secrets(text, secrets)
                if complete
                else "[WITHHELD incomplete CLI content]"
            )
    return [redact_granted_secrets(event, secrets) for event in output]
