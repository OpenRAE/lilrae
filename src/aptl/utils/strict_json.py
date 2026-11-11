"""Unambiguous JSON decoding for signed and security-sensitive documents."""

from __future__ import annotations

import json
import math
from typing import NoReturn

from pydantic import BaseModel

type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)


def _closed_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    """Build one object while rejecting ambiguous duplicate member names."""

    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    """Reject non-finite JSON constants accepted by Python's decoder."""

    raise ValueError(f"invalid JSON constant: {value}")


def _finite_float(text: str) -> float:
    """Reject a JSON number that overflows to a non-finite float."""

    value = float(text)
    if not math.isfinite(value):
        raise ValueError("JSON number out of range")
    return value


def loads_strict(payload: bytes | str) -> JsonValue:
    """Decode JSON while rejecting duplicate keys and non-finite numbers."""

    return json.loads(
        payload,
        object_pairs_hook=_closed_object,
        parse_constant=_reject_constant,
        parse_float=_finite_float,
    )


def model_validate_json_strict[ModelT: BaseModel](
    model_type: type[ModelT], payload: bytes | str
) -> ModelT:
    """Reject ambiguous JSON, then retain Pydantic's JSON-aware strict coercion."""

    loads_strict(payload)
    return model_type.model_validate_json(payload)
