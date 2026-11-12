"""Strict Base64 transport of byte fields in the containment documents."""

import base64
import binascii
from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer


def _decode(value: object) -> object:
    """Decode a wire string; pass bytes from Python callers through."""
    if not isinstance(value, str):
        return value
    try:
        return base64.b64decode(value, validate=True)
    except binascii.Error as exc:
        raise ValueError("value is not valid Base64") from exc


def _encode(value: bytes) -> str:
    """Encode bytes as standard Base64 text."""
    return base64.b64encode(value).decode("ascii")


type Base64Payload = Annotated[
    bytes,
    BeforeValidator(_decode),
    PlainSerializer(_encode, return_type=str, when_used="json"),
]
