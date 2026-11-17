"""Read progress timeout shared by core collection and native backend reads.

An evidence read fails as a timeout only when it receives no new data for the
progress timeout. A source that keeps delivering data never times out, so the
timeout never limits how much evidence a capture retains.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

#: Default seconds without new data before a read fails. No measurements of
#: read stalls exist yet, so the default is deliberately long.
DEFAULT_PROGRESS_TIMEOUT_SECONDS = 1800.0

_PROGRESS_TIMEOUT: ContextVar[float] = ContextVar(
    "capture_progress_timeout", default=DEFAULT_PROGRESS_TIMEOUT_SECONDS
)


@contextmanager
def progress_timeout(seconds: float) -> Iterator[None]:
    """Make ``seconds`` the progress timeout of nested native reads."""
    if seconds <= 0:
        raise ValueError("progress timeout must be positive")
    token = _PROGRESS_TIMEOUT.set(seconds)
    try:
        yield
    finally:
        _PROGRESS_TIMEOUT.reset(token)


def current_progress_timeout() -> float:
    """Return the progress timeout that applies to the current read."""
    return _PROGRESS_TIMEOUT.get()
