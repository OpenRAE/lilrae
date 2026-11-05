"""Remove explicitly granted credential values before shared policy redaction."""

import json
from ._redaction_patterns import REDACTED


def _erase_text(text: str, granted: tuple[str, ...], depth: int, limit: int) -> str:
    """Handle JSON encoded in text before replacing exact granted values."""
    if text.lstrip().startswith(("{", "[")):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, (dict, list)):
                return json.dumps(
                    _erase(parsed, granted, depth + 1, limit), separators=(",", ":")
                )
        except ValueError:
            # Malformed JSON still receives exact literal redaction below.
            pass
    for secret in granted:
        text = text.replace(secret, REDACTED)
    return text


def _erase(item: object, granted: tuple[str, ...], depth: int, limit: int) -> object:
    """Bound recursion while removing exact grants from keys and values."""
    if depth >= limit:
        return REDACTED
    result = item
    if isinstance(item, str):
        result = _erase_text(item, granted, depth, limit)
    elif isinstance(item, dict):
        result = {
            _erase(key, granted, depth + 1, limit): _erase(
                child, granted, depth + 1, limit
            )
            for key, child in item.items()
        }
    elif isinstance(item, (tuple, list)):
        result = [_erase(child, granted, depth + 1, limit) for child in item]
    return result


def erase_granted_secrets(
    value: object, secrets: tuple[str, ...], limit: int
) -> object:
    """Remove only supplied grants; no environment or credential discovery occurs."""
    if any(not isinstance(secret, str) for secret in secrets):
        raise TypeError("credential redaction requires string grants")
    granted = tuple(
        sorted({secret for secret in secrets if secret}, key=len, reverse=True)
    )
    return _erase(value, granted, 0, limit) if granted else value
