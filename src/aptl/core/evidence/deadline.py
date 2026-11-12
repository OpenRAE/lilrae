"""Capture deadlines shared by core collection and native backend reads."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_DEADLINE: ContextVar[tuple[float, Callable[[], float]] | None] = ContextVar(
    "capture_read_deadline", default=None
)


@contextmanager
def native_read_budget(expires: float, clock: Callable[[], float]) -> Iterator[None]:
    """Keep the absolute expiry visible through nested native reads."""
    token = _DEADLINE.set((expires, clock))
    try:
        yield
    finally:
        _DEADLINE.reset(token)


def native_read_timeout(timeout: int | float | None) -> int | float | None:
    """Clamp a native operation without giving it a new deadline."""
    budget = _DEADLINE.get()
    if budget is None:
        return timeout
    expires, clock = budget
    remaining = expires - clock()
    if remaining <= 0:
        raise TimeoutError("capture read deadline expired")
    return remaining if timeout is None else min(timeout, remaining)
