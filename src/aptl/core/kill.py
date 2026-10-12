"""Emergency kill switch for agent, MCP, and lab operations."""

import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TypedDict

from aptl.core.kill_containers import kill_lab_containers
from aptl.core.lifecycle_guard import (
    LifecycleLockUnavailableError,
    lifecycle_mutation_lock,
)
from aptl.core.lifecycle_policy import LifecycleBusyError
from aptl.core.session import clean_trace_context, clear_session
from aptl.utils.logging import get_logger

log = get_logger("kill")

# Windows has no SIGKILL. There, os.kill maps any non-CTRL_* signal to
# TerminateProcess, which is itself an uncatchable, forceful kill -- the
# SIGKILL equivalent -- so SIGTERM is the correct escalation target. On POSIX
# this resolves to the real SIGKILL and behaviour is unchanged.
_FORCE_KILL_SIGNAL = getattr(signal, "SIGKILL", signal.SIGTERM)


class McpProcess(TypedDict):
    """A discovered MCP server process."""

    pid: int
    cmdline: str
    name: str


MCP_SERVER_NAMES = [
    "mcp-wazuh",
    "mcp-red",
    "mcp-reverse",
    "mcp-soar",
    "mcp-indexer",
    "mcp-casemgmt",
    "mcp-network",
    "mcp-threatintel",
]


@dataclass
class KillResult:
    """Result of the kill switch operation."""

    success: bool
    mcp_processes_killed: int = 0
    mcp_discovery_unavailable: bool = False
    containers_stopped: bool = False
    session_cleared: bool = False
    trace_context_cleaned: bool = False
    errors: list[str] = field(default_factory=list)


class McpDiscoveryUnavailableError(RuntimeError):
    """The kill could not look for MCP server processes on this host."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"MCP process discovery is unavailable: {reason}. Any MCP servers "
            "that are running were not stopped; end each node process running "
            "an mcp-*/build/index.js server by hand, for example with Task "
            "Manager or Stop-Process on Windows."
        )


def find_mcp_processes() -> list[McpProcess]:
    """Discover running MCP server Node.js processes.

    Scans ``/proc/*/cmdline`` on Linux for processes whose command line
    contains a known MCP server build path (e.g. ``mcp-wazuh/build/index.js``).
    Falls back to ``pgrep -f`` on non-Linux platforms.

    Returns:
        List of dicts with keys ``pid`` (int), ``cmdline`` (str), and
        ``name`` (str, the matched server name).

    Raises:
        McpDiscoveryUnavailableError: ``pgrep`` is needed but cannot run,
            as on native Windows, or it runs and reports an error.
    """
    if sys.platform == "linux":
        return _find_via_proc()
    return _find_via_pgrep()


def _find_via_proc() -> list[McpProcess]:
    """Scan /proc for MCP server processes.

    Skips the current process to avoid false-positive matches when the
    kill switch's own command line happens to contain an MCP server name
    (e.g. in log messages or grep patterns).
    """
    found: list[McpProcess] = []
    own_pid = os.getpid()
    try:
        entries = os.listdir("/proc")
    except OSError:
        log.warning("Cannot read /proc, falling back to pgrep")
        return _find_via_pgrep()

    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid == own_pid:
            continue
        cmdline_path = f"/proc/{pid}/cmdline"
        try:
            with open(cmdline_path, "rb") as f:
                raw = f.read()
        except OSError:
            continue

        cmdline = raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
        for name in MCP_SERVER_NAMES:
            if f"{name}/build/index.js" in cmdline:
                found.append({"pid": pid, "cmdline": cmdline, "name": name})
                break

    return found


def _find_via_pgrep() -> list[McpProcess]:
    """Discover MCP processes using pgrep (non-Linux fallback).

    A ``pgrep`` that cannot run, or exits with neither 0 (a match) nor 1 (no
    match), raises instead of returning an empty list: a host that cannot
    look must not report that no MCP server is running.
    """
    found: list[McpProcess] = []
    for name in MCP_SERVER_NAMES:
        pattern = f"{name}/build/index.js"
        try:
            result = subprocess.run(
                ["pgrep", "-f", pattern],
                capture_output=True,
                text=True,
            )
            if result.returncode not in (0, 1):
                stderr = result.stderr.strip().splitlines() or ["no error output"]
                status = f"pgrep exited with status {result.returncode}"
                raise McpDiscoveryUnavailableError(f"{status} ({stderr[0]})")
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    pid = int(line.strip())
                    found.append({"pid": pid, "cmdline": pattern, "name": name})
        except OSError as exc:
            raise McpDiscoveryUnavailableError(f"pgrep could not run ({exc})") from exc
        except ValueError:
            continue
    return found


def _process_exited(pid: int) -> bool:
    """Check whether a process has exited.

    Uses ``os.kill(pid, 0)`` which sends no signal but checks existence.
    Returns True if the process is gone (``ProcessLookupError``) or if
    we lack permission to signal it (``PermissionError``).  In the
    permission case the process may still be alive, but since we also
    cannot SIGKILL it there is no point waiting further.
    """
    try:
        os.kill(pid, 0)
        return False
    except (ProcessLookupError, PermissionError):
        return True


def _verify_mcp_process(pid: int) -> bool:
    """Verify that *pid* still belongs to an MCP server process.

    Re-reads ``/proc/{pid}/cmdline`` and checks for known MCP server
    patterns.  Returns False if the process is gone, unreadable, or no
    longer matches an MCP server — preventing SIGKILL to a recycled PID.
    """
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            raw = f.read()
    except OSError:
        return False
    cmdline = raw.replace(b"\x00", b" ").decode("utf-8", errors="replace")
    return any(f"{name}/build/index.js" in cmdline for name in MCP_SERVER_NAMES)


def _sigterm_processes(processes: list[McpProcess]) -> tuple[list[int], list[str]]:
    """Send SIGTERM to each process; return (tracked pids, error messages)."""
    pids_to_track: list[int] = []
    errors: list[str] = []
    for proc in processes:
        pid = proc["pid"]
        try:
            os.kill(pid, signal.SIGTERM)
            pids_to_track.append(pid)
            log.info("Sent SIGTERM to %s (pid=%d)", proc["name"], pid)
        except ProcessLookupError:
            log.debug("Process %d already dead", pid)
        except PermissionError:
            errors.append(f"Permission denied killing {proc['name']} (pid={pid})")
            log.warning("Permission denied sending SIGTERM to pid=%d", pid)
    return pids_to_track, errors


def _await_graceful_exit(
    pids: list[int],
    timeout: float,
    time_source: Callable[[], float],
    sleep: Callable[[float], None],
) -> list[int]:
    """Wait up to *timeout* seconds for *pids* to exit; return the survivors."""
    deadline = time_source() + timeout
    remaining = list(pids)
    while remaining and time_source() < deadline:
        remaining = [pid for pid in remaining if not _process_exited(pid)]
        if remaining:
            sleep(0.25)
    return remaining


def _sigkill_survivors(pids: list[int]) -> list[str]:
    """SIGKILL each survivor (re-verifying PID identity on Linux); return errors."""
    errors: list[str] = []
    for pid in pids:
        if sys.platform == "linux" and not _verify_mcp_process(pid):
            log.warning("PID %d is no longer an MCP process, skipping SIGKILL", pid)
            continue
        try:
            os.kill(pid, _FORCE_KILL_SIGNAL)
            log.warning("Sent SIGKILL to pid=%d (did not exit after SIGTERM)", pid)
        except ProcessLookupError:
            pass
        except PermissionError:
            errors.append(f"Permission denied force-killing pid={pid}")
    return errors


def kill_mcp_processes(
    timeout: float = 5.0,
    *,
    time_source: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[int, list[str]]:
    """Terminate all running MCP server processes.

    Sends SIGTERM first, waits up to *timeout* seconds for graceful
    shutdown (allowing OTel span flush), then sends SIGKILL to any
    survivors.

    Args:
        timeout: Seconds to wait after SIGTERM before sending SIGKILL.
        time_source: Monotonic clock, injectable so tests drive the deadline
            with an explicit value sequence instead of patching the module.
        sleep: Sleep function, injectable so tests don't actually block.

    Returns:
        Tuple of (number of processes killed, list of error messages).

    Raises:
        McpDiscoveryUnavailableError: The host cannot look for MCP server
            processes, so none was signalled.
    """
    processes = find_mcp_processes()
    if not processes:
        log.info("No MCP server processes found")
        return 0, []

    log.info(
        "Found %d MCP server process(es): %s",
        len(processes),
        ", ".join(f"{p['name']}(pid={p['pid']})" for p in processes),
    )

    pids_to_track, errors = _sigterm_processes(processes)
    survivors = _await_graceful_exit(pids_to_track, timeout, time_source, sleep)
    errors.extend(_sigkill_survivors(survivors))

    killed = len(processes) - len(errors)
    log.info("Killed %d MCP server process(es)", killed)
    return killed, errors


def execute_kill(
    containers: bool = False,
    project_dir: Optional[Path] = None,
) -> KillResult:
    """Execute the full kill switch under the shared project mutation owner."""

    resolved_dir = Path(project_dir) if project_dir else Path(".")
    try:
        with lifecycle_mutation_lock(resolved_dir) as project_root:
            return _execute_kill_owned(containers, project_root)
    except LifecycleBusyError:
        return KillResult(
            success=False,
            errors=[
                "[lifecycle-owner-busy] Another lab lifecycle operation is active; "
                "the kill switch did not mutate project state."
            ],
        )
    except LifecycleLockUnavailableError:
        return KillResult(
            success=False,
            errors=[
                "[lifecycle-lock-unavailable] The kill switch could not establish "
                "safe project lifecycle ownership."
            ],
        )


def _execute_kill_owned(containers: bool, resolved_dir: Path) -> KillResult:
    """Execute the emergency kill switch.

    Runs each step independently so that a failure in one does not
    prevent the others from executing.

    Args:
        containers: If True, also force-stop all lab containers.
        project_dir: APTL project directory (defaults to cwd).

    Returns:
        KillResult with details of what was done.
    """
    state_dir = resolved_dir / ".aptl"
    errors: list[str] = []

    # Step 1: Kill MCP processes (highest priority)
    mcp_killed = 0
    mcp_discovery_unavailable = False
    try:
        mcp_killed, mcp_errors = kill_mcp_processes()
        errors.extend(mcp_errors)
    except McpDiscoveryUnavailableError as exc:
        mcp_discovery_unavailable = True
        msg = str(exc)
        log.error(msg)
        errors.append(msg)
    except Exception as exc:
        msg = f"MCP process kill failed: {exc}"
        log.error(msg)
        errors.append(msg)

    # Step 2: Kill lab containers (if requested)
    containers_stopped = False
    if containers:
        try:
            containers_stopped, container_error = kill_lab_containers(
                project_dir=resolved_dir,
            )
            if container_error:
                errors.append(container_error)
        except Exception as exc:
            msg = f"Container kill failed: {exc}"
            log.error(msg)
            errors.append(msg)

    # Step 3: Clear session state
    session_cleared = False
    try:
        session_cleared = clear_session(state_dir)
    except Exception as exc:
        msg = f"Session clear failed: {exc}"
        log.error(msg)
        errors.append(msg)

    # Step 4: Clean up trace context
    trace_cleaned = False
    try:
        trace_cleaned = clean_trace_context(state_dir)
    except Exception as exc:
        msg = f"Trace context cleanup failed: {exc}"
        log.error(msg)
        errors.append(msg)

    # Success if any step accomplished something, or if there was simply
    # nothing to kill (no errors). A kill that could not look for MCP servers
    # fails either way: the servers it exists to stop may still be running.
    any_action = (
        mcp_killed > 0 or containers_stopped or session_cleared or trace_cleaned
    )
    success = (any_action or len(errors) == 0) and not mcp_discovery_unavailable

    result = KillResult(
        success=success,
        mcp_processes_killed=mcp_killed,
        mcp_discovery_unavailable=mcp_discovery_unavailable,
        containers_stopped=containers_stopped,
        session_cleared=session_cleared,
        trace_context_cleaned=trace_cleaned,
        errors=errors,
    )

    log.info(
        "Kill switch complete: mcp=%d containers=%s session=%s trace=%s errors=%d",
        mcp_killed,
        containers_stopped,
        session_cleared,
        trace_cleaned,
        len(errors),
    )
    return result
