"""Strict JSON decoding rejects each number that is not finite (#1610)."""

from __future__ import annotations

import pytest

from aptl.utils.strict_json import loads_strict


@pytest.mark.parametrize("payload", ["1e400", "-1e400", "[1e999]", '{"a": -1e309}'])
def test_strict_decoding_rejects_numbers_that_overflow(payload: str) -> None:
    with pytest.raises(ValueError, match="JSON number out of range"):
        loads_strict(payload)


def test_strict_decoding_keeps_finite_numbers() -> None:
    assert loads_strict('{"a": 1.5e308, "b": 5e-324, "c": 1e-400, "d": 7}') == {
        "a": 1.5e308,
        "b": 5e-324,
        "c": 0.0,
        "d": 7,
    }
