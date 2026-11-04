"""Absolute cleanup and capture deadlines shared by nested Docker reads."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from time import monotonic

from aptl.core.deployment.errors import BackendTimeoutError
from aptl.core.evidence.deadline import native_read_timeout


@dataclass(frozen=True)
class CleanupDeadline:
    """A fixed expiry shared by every operation in one cleanup obligation."""

    expires: float
    clock: Callable[[], float]

    def remaining(self) -> float:
        remaining = self.expires - self.clock()
        if remaining <= 0:
            raise BackendTimeoutError("declared cleanup deadline expired")
        return remaining


_DEADLINE: ContextVar[CleanupDeadline | None] = ContextVar(
    "cleanup_deadline", default=None
)


@contextmanager
def cleanup_budget(
    seconds: int, clock: Callable[[], float] = monotonic
) -> Iterator[CleanupDeadline]:
    """Cap all nested backend calls without changing its configured transport."""
    if seconds <= 0:
        raise ValueError("cleanup budget must be positive")
    budget = CleanupDeadline(clock() + seconds, clock)
    token = _DEADLINE.set(budget)
    try:
        yield budget
    finally:
        _DEADLINE.reset(token)


def cleanup_command_timeout(timeout: int | float | None) -> int | float | None:
    """Preserve ordinary timeouts outside cleanup; clamp them inside cleanup."""
    budget = _DEADLINE.get()
    if budget is not None:
        remaining = budget.remaining()
        timeout = remaining if timeout is None else min(timeout, remaining)
    try:
        return native_read_timeout(timeout)
    except TimeoutError:
        raise BackendTimeoutError("capture read deadline expired") from None
