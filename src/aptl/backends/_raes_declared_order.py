"""Report observed records in the order that the scenario declares them.

RAES compares a prepared value with its readback by position when a
constraint document governs it. Readback finds records in native order, for
example sorted by path or port. This module puts each observed record list
in the declared order, matched by a record identity, so the two compare
record by record. It changes no record and drops none.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

_NAMED_IDENTITIES = ("path", "username", "name")


def _identity(observed: Sequence[Mapping], declared: Sequence[Mapping]) -> str | None:
    """Return one key that names every record uniquely in both lists."""
    common = set.intersection(*(set(item) for item in (*observed, *declared)))
    candidates = sorted(key for key in common if key.endswith("_id")) + [
        key for key in _NAMED_IDENTITIES if key in common
    ]
    for key in candidates:
        if all(
            len({repr(item[key]) for item in items}) == len(items)
            for items in (observed, declared)
        ):
            return key
    return None


def in_declared_order(observed: object, declared: object) -> object:
    """Return ``observed`` with every record list in its declared order."""
    if isinstance(observed, Mapping) and isinstance(declared, Mapping):
        return {key: in_declared_order(value, declared.get(key)) for key, value in observed.items()}
    if (
        isinstance(observed, list)
        and isinstance(declared, list)
        and observed
        and declared
        and all(isinstance(item, Mapping) for item in (*observed, *declared))
    ):
        key = _identity(observed, declared)
        if key is None:
            return observed
        rank = {repr(item[key]): index for index, item in enumerate(declared)}
        by_identity = {repr(item[key]): item for item in declared}
        ordered = sorted(observed, key=lambda item: rank.get(repr(item[key]), len(rank)))
        return [in_declared_order(item, by_identity.get(repr(item[key]))) for item in ordered]
    return observed


__all__ = ["in_declared_order"]
