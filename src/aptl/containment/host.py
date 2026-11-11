"""Host checks for the Bubblewrap engine; each one answers for one layer."""

import ctypes
import ctypes.util
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from aptl.containment.bubblewrap import LAUNCHER_PYTHON, parse_version, probe_arguments
from aptl.core.agent_errors import AgentExecutionError
from aptl.core.containment import WorkerRunner

MINIMUM_BUBBLEWRAP = (0, 8, 0)  # --disable-userns
MINIMUM_LIBSECCOMP = (2, 5, 0)
_LANDLOCK_CREATE_RULESET = 444
_LANDLOCK_CREATE_RULESET_VERSION = 1
_PROBE_SECONDS = 30.0
_PROBE_OUTPUT_BYTES = 65536
_HOST_PATH = {"PATH": "/usr/bin:/bin"}


class _SeccompVersion(ctypes.Structure):
    _fields_ = (("major", ctypes.c_uint), ("minor", ctypes.c_uint), ("micro", ctypes.c_uint))


@dataclass(frozen=True)
class HostFacts:
    """What the host can deliver; None means the check could not decide."""

    bubblewrap_version: str | None
    bubblewrap_supported: bool
    namespaces: bool | None
    landlock_abi: int | None
    libseccomp_version: str | None
    libseccomp_supported: bool
    launcher_python: bool


def landlock_abi() -> int | None:
    """Return the kernel's Landlock ABI version, or None without Landlock."""
    libc = ctypes.CDLL(None, use_errno=True)
    version = libc.syscall(_LANDLOCK_CREATE_RULESET, None, 0, _LANDLOCK_CREATE_RULESET_VERSION)
    return version if version > 0 else None


def libseccomp_version() -> tuple[int, int, int] | None:
    """Return the installed libseccomp version, or None when it does not load."""
    name = ctypes.util.find_library("seccomp") or "libseccomp.so.2"
    try:
        library = ctypes.CDLL(name)
    except OSError:
        return None
    library.seccomp_version.restype = ctypes.POINTER(_SeccompVersion)
    version = library.seccomp_version().contents
    return (version.major, version.minor, version.micro)


class HostInspector:
    """Observe the host before each run; nothing is cached between runs."""

    def __init__(
        self,
        runner: WorkerRunner,
        bubblewrap: Path,
        *,
        cwd: Path,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._runner = runner
        self._bubblewrap = bubblewrap
        self._cwd = cwd
        self._clock = clock

    def observe(self, *, deadline: float | None = None, cancel_event: Event | None = None) -> HostFacts:
        """Check each layer separately within the run's deadline and cancellation."""
        control = (deadline, cancel_event)
        version = self._bubblewrap_version(control)
        supported = version is not None and version >= MINIMUM_BUBBLEWRAP
        seccomp = libseccomp_version()
        return HostFacts(
            bubblewrap_version=".".join(map(str, version)) if version else None,
            bubblewrap_supported=supported,
            namespaces=self._namespaces(control) if supported else None,
            landlock_abi=landlock_abi(),
            libseccomp_version=".".join(map(str, seccomp)) if seccomp else None,
            libseccomp_supported=seccomp is not None and seccomp >= MINIMUM_LIBSECCOMP,
            launcher_python=os.access(LAUNCHER_PYTHON, os.X_OK),
        )

    def _run(
        self, argv: tuple[str, ...], control: tuple[float | None, Event | None]
    ) -> tuple[int, bytes] | None:
        deadline, cancel_event = control
        budget = _PROBE_SECONDS if deadline is None else min(_PROBE_SECONDS, deadline - self._clock())
        if budget <= 0:
            return None
        try:
            result = self._runner.run(
                argv, env=dict(_HOST_PATH), cwd=self._cwd, stdin=b"",
                timeout_seconds=budget, max_output_bytes=_PROBE_OUTPUT_BYTES,
                cancel_event=cancel_event,
            )
        except (AgentExecutionError, OSError):
            return None
        return result.returncode, result.stdout

    def _bubblewrap_version(self, control: tuple[float | None, Event | None]) -> tuple[int, ...] | None:
        if not os.access(self._bubblewrap, os.X_OK):
            return None
        observed = self._run((str(self._bubblewrap), "--version"), control)
        return parse_version(observed[1]) if observed and observed[0] == 0 else None

    def _namespaces(self, control: tuple[float | None, Event | None]) -> bool | None:
        observed = self._run(probe_arguments(self._bubblewrap), control)
        return None if observed is None else observed[0] == 0
