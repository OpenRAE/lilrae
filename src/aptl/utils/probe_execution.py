"""Scoped use of the existing bounded process runner for read-only probes."""

import os
import subprocess
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ProbeCleanup(Protocol):
    residual: tuple[str, ...]


class ProbeProcessResult(Protocol):
    returncode: int
    stdout: bytes
    stderr: bytes
    cleanup: ProbeCleanup | None


class ProbeProcessRunner(Protocol):
    """Implemented by the canonical participant BoundedProcessRunner."""

    def run(
        self,
        argv: tuple[str, ...],
        *,
        env: dict[str, str],
        cwd: Path,
        stdin: bytes,
        timeout_seconds: float,
        max_output_bytes: int,
    ) -> ProbeProcessResult: ...


@dataclass
class ProbeExecutionScope:
    runner: ProbeProcessRunner
    max_output_bytes: int
    cessation_confirmed: bool = True


_SCOPE: ContextVar[ProbeExecutionScope | None] = ContextVar(
    "bounded_readiness_probe", default=None
)


def probe_output_byte_limit() -> int | None:
    """Return the active acquisition bound for native file and source owners."""
    scope = _SCOPE.get()
    return scope.max_output_bytes if scope is not None else None


def note_probe_cessation(confirmed: bool) -> None:
    """Carry a native owner's unresolved process cleanup into the shared gate."""
    scope = _SCOPE.get()
    if scope is not None and confirmed is not True:
        scope.cessation_confirmed = False


@contextmanager
def bounded_probe_commands(
    runner: ProbeProcessRunner, max_output_bytes: int
) -> Iterator[ProbeExecutionScope]:
    scope = ProbeExecutionScope(runner, max_output_bytes)
    token = _SCOPE.set(scope)
    try:
        yield scope
    finally:
        _SCOPE.reset(token)


def run_bounded_probe_command(
    argv: list[str],
    *,
    cwd: Path,
    timeout: float,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str] | None:
    """Return None outside readiness; otherwise bound bytes during acquisition."""
    scope = _SCOPE.get()
    if scope is None:
        return None
    try:
        result = scope.runner.run(
            tuple(argv),
            env=dict(os.environ if env is None else env),
            cwd=cwd,
            stdin=b"",
            timeout_seconds=timeout,
            max_output_bytes=scope.max_output_bytes,
        )
    except Exception as exc:
        cleanup = getattr(exc, "cleanup", None)
        if cleanup is None or cleanup.residual:
            scope.cessation_confirmed = False
        raise RuntimeError("bounded-probe-command-failed") from None
    if result.cleanup is None or result.cleanup.residual:
        scope.cessation_confirmed = False
        raise RuntimeError("bounded-probe-cessation-unverified")
    if len(result.stdout) + len(result.stderr) > scope.max_output_bytes:
        raise RuntimeError("bounded-probe-output-invalid")
    return subprocess.CompletedProcess(
        argv,
        result.returncode,
        result.stdout.decode("utf-8", errors="replace"),
        result.stderr.decode("utf-8", errors="replace"),
    )
