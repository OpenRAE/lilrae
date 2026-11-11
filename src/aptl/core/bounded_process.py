"""The fixed inputs of one bounded child process.

Core owns the request so that a lower-layer consumer, such as the containment
adapter, can build it and hand it to the application's ``BoundedProcessRunner``.
"""

from dataclasses import dataclass, field
from pathlib import Path
from threading import Event


@dataclass(frozen=True)
class ProcessRequest:
    """One invocation's fixed inputs; private bytes never enter its repr.

    ``pass_fds`` names the only descriptors besides standard I/O that the
    child inherits.
    """

    argv: tuple[str, ...]
    env: dict[str, str] = field(repr=False)
    cwd: Path
    stdin: bytes = field(repr=False)
    timeout_seconds: float
    max_output_bytes: int
    cancel_event: Event | None = None
    pass_fds: tuple[int, ...] = ()
