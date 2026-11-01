"""One authored cleanup deadline shared by nested Docker readback calls."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from time import monotonic

from aptl.core.deployment.errors import BackendTimeoutError


@dataclass(frozen=True)
class CleanupDeadline:
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
    if budget is None:
        return timeout
    remaining = budget.remaining()
    return remaining if timeout is None else min(timeout, remaining)
