"""Ports of the shared containment interface."""

from pathlib import Path
from threading import Event
from typing import Protocol, runtime_checkable

from aptl.core.containment.report import ExecutionReport
from aptl.core.containment.request import ExecutionRequest


class ContainmentAdapter(Protocol):
    """Run one request inside a native boundary and report the result."""

    def execute(
        self, request: ExecutionRequest, *, cancel_event: Event | None = None
    ) -> ExecutionReport: ...


class WorkerCleanup(Protocol):
    """The runner's cleanup observation for one worker process group."""

    @property
    def residual(self) -> tuple[str, ...]: ...

    @property
    def seconds(self) -> float: ...


class WorkerResult(Protocol):
    """The worker's exit status, bounded output, and cleanup observation."""

    @property
    def returncode(self) -> int: ...

    @property
    def stdout(self) -> bytes: ...

    @property
    def stderr(self) -> bytes: ...

    @property
    def cleanup(self) -> WorkerCleanup | None: ...


@runtime_checkable
class WorkerRunnerFailure(Protocol):
    """A runner error that carries its reason and its cleanup observation."""

    @property
    def reason(self) -> str: ...

    @property
    def cleanup(self) -> WorkerCleanup: ...

    @property
    def stdout_bytes(self) -> int: ...

    @property
    def stderr_bytes(self) -> int: ...


class WorkerRunner(Protocol):
    """Implemented by the canonical cancellable ``BoundedProcessRunner``."""

    def run(
        self,
        argv: tuple[str, ...],
        *,
        env: dict[str, str],
        cwd: Path,
        stdin: bytes,
        timeout_seconds: float,
        max_output_bytes: int,
        cancel_event: Event | None = None,
        pass_fds: tuple[int, ...] = (),
    ) -> WorkerResult: ...
