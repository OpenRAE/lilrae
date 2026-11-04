"""Bound serialized capture after its owner has applied the redaction policy."""

from collections.abc import Mapping
import json


def capture_prefix(
    payload: object, identity: Mapping[str, object], limit: int
) -> dict[str, object]:
    """Bound an already prepared payload inside valid JSON, including metadata."""
    text = json.dumps(payload, separators=(",", ":"), allow_nan=False)
    result = {
        **identity,
        "complete": False,
        "required_usage_complete": False,
        "truncated": True,
        "loss_disclosure": "source exceeded the capture byte limit",
        "partial_payload": "",
    }

    def size() -> int:
        return len(
            json.dumps([result], separators=(",", ":"), allow_nan=False).encode()
        )

    if size() > limit:
        raise BufferError("capture identity exceeds its byte limit")
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        result["partial_payload"] = text[:middle]
        if size() <= limit:
            low = middle
        else:
            high = middle - 1
    result["partial_payload"] = text[:low]
    return result
