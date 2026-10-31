"""Bounded subprocess execution for the participant workbench.

One invocation is one child started in a new session, so the child and every
descendant that stays in its process group are invocation-owned. The runner
keeps two separate bounds:

- **The deadline** is monotonic and starts before launch. It covers launch,
  standard-input delivery and output capture. Input and output move through
  non-blocking pipes, so a child that never reads its input, a full pipe, or a
  descendant that keeps the output streams open cannot hold the runner past
  it. Output ends when the runner sees the child exit: it keeps what is then
  waiting in the pipes, which is everything the child wrote.
- **Cleanup** follows every outcome: success, error, cancellation or timeout.
  It signals the whole process group while the group still exists, reaps the
  child and waits a bounded time for the output streams to close. It is timed
  and reported apart from the deadline. Once the child has exited on its own,
  its helpers, such as the MCP servers a provider CLI started, get a longer
  SIGTERM grace period to finish a graceful shutdown; a child stopped at a
  limit or by cancellation gets the short one, so the deadline stays tight.

Process supervision is not OS isolation. Cleanup reaches the process group and
nothing else, so processes outside it, such as scenario-owned persistent
services, keep their declared lifecycle. A descendant that leaves the group is
out of reach too; cleanup reports one only while it still holds the output
streams. Residue is what cleanup can observe without trusting an errno: a
child it could not reap, output streams still held open, or a process group
whose disappearance it could not confirm. The last case can include unreaped
zombies or a permission failure; it does not assert that a helper is live.
Reports name these facts, never argv, environment or output.
"""

from __future__ import annotations

import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Protocol

from aptl.core.agent_errors import AgentExecutionError as AgentExecutionError

from aptl.workbench._pipe_exchange import POLL_SECONDS, PipeExchange

# Cleanup bounds, each applied once: the SIGTERM grace period for the group,
# reaping the child after SIGKILL, and waiting for the output streams to close.
# The grace period depends on how the invocation ended. When the runner stops
# a child that is still running, at a timeout or an overflow, or the request is
# cancelled, the group gets the short one.
_TERM_GRACE_SECONDS = 1.0
# After the child has exited on its own, its remaining helpers are winding
# down, so they get time to finish a graceful shutdown before SIGKILL. The
# common MCP server's shutdown (mcp/aptl-mcp-common/src/server.ts) awaits
# sshManager.disconnectAll(), which allows each session up to
# REMOTE_CLOSE_AWAIT (3 s) for its remote close and each connection up to
# SESSION_CLOSE (5 s), both in mcp/aptl-mcp-common/src/ssh-contracts.ts. Its
# trace flush is bounded well inside the OTLP exporter's default 10 s timeout,
# which this budget still allows. The other 2 s cover the signal delivery and
# the process exit. The same shutdown also finalizes and harvests open capture
# sessions; that work has no place in this bound, and lab stop does not depend
# on it (ADR-042). A group that ends sooner ends the wait sooner.
_SHUTDOWN_GRACE_SECONDS = 20.0
_REAP_SECONDS = 1.0
_RELEASE_SECONDS = 1.0

# Why a bounded invocation failed: BoundedProcessError.reason is one of these.
REASON_TIMEOUT = "agent request exceeded the configured timeout"
REASON_CANCELLED = "agent request was cancelled"
REASON_OVERFLOW = "agent output exceeded the configured limit"
REASON_RESIDUE = "agent process cleanup left residual processes"
_RESIDUAL_AGENT_RUNNING = "agent-process-running"
_RESIDUAL_STREAMS_HELD = "output-streams-held"
_RESIDUAL_GROUP_UNCONFIRMED = "process-group-cleanup-unconfirmed"


@dataclass(frozen=True)
class ProcessCleanup:
    """How cleanup of one invocation's process group ended.

    Timed apart from the invocation deadline. ``residual`` names what cleanup
    could still observe afterwards; it never carries argv, environment or
    output.
    """

    process_group: int
    seconds: float
    residual: tuple[str, ...] = ()

    def summary(self) -> str:
        """Describe the cleanup without any process content."""

        return (
            f"process group {self.process_group} cleanup took "
            f"{self.seconds:.2f}s; residual: {self.residual_summary()}"
        )

    def residual_summary(self) -> str:
        """Name what cleanup could still observe, or say that it saw nothing."""

        return ", ".join(self.residual) or "none observed"

    def record(self) -> dict[str, object]:
        """Return the cleanup as a JSON-ready record for run evidence."""

        return {
            "process_group": self.process_group,
            "seconds": self.seconds,
            "residual": list(self.residual),
        }


@dataclass(frozen=True)
class ProcessResult:
    """Bounded child result returned by the process runner."""

    returncode: int
    stdout: bytes
    stderr: bytes
    cleanup: ProcessCleanup | None = None


class BoundedProcessError(AgentExecutionError):
    """A bounded invocation stopped early or its cleanup left residue.

    Carries only safe facts: the reason, how much captured output was
    withheld, and the separately timed cleanup.
    """

    def __init__(
        self,
        reason: str,
        *,
        cleanup: ProcessCleanup,
        stdout_bytes: int,
        stderr_bytes: int,
    ) -> None:
        super().__init__(
            f"{reason}; withheld captured output (stdout {stdout_bytes} bytes, "
            f"stderr {stderr_bytes} bytes); {cleanup.summary()}"
        )
        self.reason = reason
        self.cleanup = cleanup
        self.stdout_bytes = stdout_bytes
        self.stderr_bytes = stderr_bytes

    def stable_summary(self) -> str:
        """Name the reason and the residue, without timings or process ids."""

        return f"{self.reason}; cleanup residual: {self.cleanup.residual_summary()}"

    def record(self) -> dict[str, object]:
        """Return the failure as a JSON-ready record for run evidence."""

        return {
            "reason": self.reason,
            "withheld_stdout_bytes": self.stdout_bytes,
            "withheld_stderr_bytes": self.stderr_bytes,
            "cleanup": self.cleanup.record(),
        }


class ProcessRunner(Protocol):
    """Execute one fixed agent request without a shell."""

    def run(
        self,
        argv: tuple[str, ...],
        *,
        env: dict[str, str],
        cwd: Path,
        stdin: bytes,
        timeout_seconds: float,
        max_output_bytes: int,
    ) -> ProcessResult: ...


class BoundedProcessRunner:
    """Run a child within one deadline, then clean up its whole process group."""

    @staticmethod
    def run(
        argv: tuple[str, ...],
        *,
        env: dict[str, str],
        cwd: Path,
        stdin: bytes,
        timeout_seconds: float,
        max_output_bytes: int,
        cancel_event: Event | None = None,
    ) -> ProcessResult:
        """Execute a child with strict time and combined-output limits."""
        if timeout_seconds <= 0 or max_output_bytes <= 0:
            raise AgentExecutionError("agent process limits are invalid")
        if cancel_event is not None and cancel_event.is_set():
            raise AgentExecutionError(REASON_CANCELLED)
        deadline = time.monotonic() + timeout_seconds
        with selectors.DefaultSelector() as selector:
            exchange = PipeExchange(selector, stdin, max_output_bytes)
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            try:
                exchange.attach(process)
                reason = _supervise(process, exchange, deadline, cancel_event)
            except BaseException as interrupted:
                # Cancellation or an unexpected error still ends the invocation.
                cleanup = _end_invocation(process, exchange, _TERM_GRACE_SECONDS)
                interrupted.add_note(cleanup.summary())
                raise
            # A child that exited on its own leaves helpers that are winding
            # down; a child stopped at a limit gets the short grace period.
            exited = process.returncode is not None
            grace = _SHUTDOWN_GRACE_SECONDS if exited else _TERM_GRACE_SECONDS
            cleanup = _end_invocation(process, exchange, grace)
        if reason is None and cleanup.residual:
            reason = REASON_RESIDUE
        if reason is not None:
            raise BoundedProcessError(
                reason,
                cleanup=cleanup,
                stdout_bytes=len(exchange.stdout),
                stderr_bytes=len(exchange.stderr),
            )
        return ProcessResult(
            process.returncode,
            bytes(exchange.stdout),
            bytes(exchange.stderr),
            cleanup,
        )


def _supervise(
    process: subprocess.Popen[bytes],
    exchange: PipeExchange,
    deadline: float,
    cancel_event: Event | None = None,
) -> str | None:
    """Exchange input and output until the child exits or a limit is reached."""

    while process.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            failure = REASON_CANCELLED
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            failure = REASON_TIMEOUT
            break
        if not exchange.pump(min(remaining, POLL_SECONDS)):
            failure = REASON_OVERFLOW
            break
    else:
        exchange.close_input()
        failure = None if exchange.drain() else REASON_OVERFLOW
    return failure


def _end_invocation(
    process: subprocess.Popen[bytes],
    exchange: PipeExchange,
    grace_seconds: float,
) -> ProcessCleanup:
    """Clean up the invocation's process group within its own fixed bound."""

    started = time.monotonic()
    exchange.stop_capture()
    exchange.close_input()
    group_ended = _terminate_process_group(process, exchange, grace_seconds)
    held = exchange.release(time.monotonic() + _RELEASE_SECONDS)
    observed = (
        (_RESIDUAL_AGENT_RUNNING, process.returncode is None),
        (_RESIDUAL_STREAMS_HELD, held),
        (_RESIDUAL_GROUP_UNCONFIRMED, not group_ended),
    )
    return ProcessCleanup(
        process_group=process.pid,
        seconds=round(time.monotonic() - started, 3),
        residual=tuple(code for code, present in observed if present),
    )


def _signal_group(pid: int, number: int) -> None:
    """Signal a whole process group, best effort.

    Neither error this can raise is actionable, and neither is evidence about
    what survived. ``ProcessLookupError`` (ESRCH) means the group had no
    member left to signal. ``PermissionError`` (EPERM) means the platform
    could not signal any member: Darwin answers EPERM once a group holds only
    unreaped zombies, because a zombie's credentials are already cleared,
    while Linux still answers 0 for them. Reading either errno as "the group
    is gone" is what made teardown stop early. Escalation below decides from
    a separate probe that trusts only ESRCH, so both are swallowed here.
    """

    try:
        os.killpg(pid, number)
    except ProcessLookupError, PermissionError:
        pass


def _group_exists(group: int) -> bool:
    """Whether any process, live or not yet reaped, may still hold ``group``.

    Signal 0 delivers nothing, and only ESRCH proves the group is gone: Linux
    answers 0 for an unreaped zombie and Darwin EPERM, which can also mean a
    live member this process may not signal. Cleanup therefore waits for
    orphaned members to be reaped by the process that adopts them.
    """

    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def _group_ended(process: subprocess.Popen[bytes]) -> bool:
    """Whether the child is reaped and nothing else holds its group id."""

    return process.poll() is not None and not _group_exists(process.pid)


def _await_group_exit(
    process: subprocess.Popen[bytes],
    exchange: PipeExchange | None,
    until: float,
) -> bool:
    """Wait until the group has ended; return False if ``until`` passes first.

    The child is reaped as soon as it exits, because an unreaped child still
    holds the group id. Output is drained meanwhile, so that a member blocked
    on a full pipe can still act on a signal.
    """

    while not _group_ended(process):
        if time.monotonic() >= until:
            return False
        if exchange is None:
            time.sleep(POLL_SECONDS)
        else:
            exchange.pump(POLL_SECONDS)
    return True


def _terminate_process_group(
    process: subprocess.Popen[bytes],
    exchange: PipeExchange | None = None,
    grace_seconds: float = _TERM_GRACE_SECONDS,
) -> bool:
    """Terminate the child's whole process group while the group exists.

    SIGTERM, a grace period of ``grace_seconds``, then SIGKILL to the whole
    group if it has not ended, whether or not the direct child has gone, then
    a bounded wait for the child to be reaped and the group to disappear.
    Return whether the group's disappearance was confirmed; sending SIGKILL
    alone is not proof of cleanup. An interrupted grace period, such as a second
    KeyboardInterrupt, still sends the SIGKILL before the interruption
    propagates.

    Escalating only when the *direct child* outlived the grace period was the
    defect: a descendant that ignores or outlives SIGTERM stayed alive
    whenever its parent died promptly, because nothing ever escalated to the
    group again. The runner's contract is that a bounded run leaves nothing
    behind, so escalation depends on the group, never on the one process the
    runner happens to hold a handle for.

    Nothing is signalled once the group is proven gone. After a success,
    ``poll()`` has already reaped the child, so its group id may be free and
    reused, and a signal sent regardless could reach a stranger's group. A
    remaining member keeps the id allocated, so a stranger could get a signal
    only if the kernel reused a freed id in the milliseconds before the next
    probe.
    """

    if _group_ended(process):
        return True
    ended = False
    try:
        _signal_group(process.pid, signal.SIGTERM)
        grace_ends = time.monotonic() + grace_seconds
        ended = _await_group_exit(process, exchange, grace_ends)
    finally:
        if not ended:
            _signal_group(process.pid, signal.SIGKILL)
    if ended:
        return True
    return _await_group_exit(process, exchange, time.monotonic() + _REAP_SECONDS)
