"""Redact logical response text before retaining fragmented transport events."""

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


def _strings(value: object, path: tuple = (), depth: int = 0):
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


def redact_response_records(
    records: list[dict], calls: list[dict], secrets: tuple[str, ...]
):
    """Keep frame metadata and combine content before redaction; withhold incomplete text."""
    output, streams, last, finished = [], {}, {}, set()
    completed = {call["request_id"] for call in calls if call["state"] == "completed"}
    withheld = False
    for original in records:
        row = dict(original)
        output.append(row)
        if row["kind"] != "response":
            continue
        payload = loads_strict(row["json"])
        request = row["request_id"]
        last[request] = row
        metadata = {key: value for key, value in payload.items() if key in _METADATA}
        choices = []
        for position, choice in enumerate(payload.get("choices", [])):
            index = choice.get("index", position)
            choices.append(
                {"index": index, "finish_reason": choice.get("finish_reason")}
            )
            if choice.get("finish_reason") or "message" in choice:
                finished.add((request, index))
            for carrier in ("delta", "message", "text"):
                if carrier not in choice:
                    continue
                try:
                    leaves = list(_strings(choice[carrier], (carrier,)))
                except ValueError:
                    withheld = True
                    row["content_withheld_reason"] = "unsupported nesting"
                    continue
                for path, text in leaves:
                    streams.setdefault((request, index, path), []).append(text)
        if choices:
            metadata["choices"] = choices
        row["json"] = json.dumps(metadata, separators=(",", ":"))
    for (request, index, path), pieces in streams.items():
        complete = request in completed and (request, index) in finished
        item = {"choice_index": index, "path": list(path)}
        if complete:
            item["value"] = redact_granted_secrets("".join(pieces), secrets)
        else:
            item["value"] = None
            item["withheld_reason"] = "incomplete streamed response"
            withheld = True
        last[request].setdefault("response_content", []).append(item)
    return [redact_granted_secrets(row, secrets) for row in output], withheld


def redact_cli_content(events: list[dict], secrets: tuple[str, ...], *, complete: bool):
    """Retain text once after combining same-kind CLI events, with original metadata."""
    output = deepcopy(events)
    for kind in ("text", "reasoning"):
        selected = [
            event
            for event in output
            if event.get("type") == kind
            and isinstance(event.get("part"), dict)
            and isinstance(event["part"].get("text"), str)
        ]
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
