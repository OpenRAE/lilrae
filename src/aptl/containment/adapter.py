"""The shared containment wrapper around the Bubblewrap engine (ADR-068).

Each run checks every property on the host, writes a private launcher policy,
and starts one Bubblewrap process through the canonical bounded runner. The
launcher and Bubblewrap report on two private status descriptors; the report
claims containment only when both confirm every property.
"""

import json
import os
import secrets
import stat
import time
from collections.abc import Callable
from pathlib import Path
from threading import Event

from aptl.containment.bubblewrap import BUBBLEWRAP, SandboxLayout, parse_status, run_arguments
from aptl.containment.host import HostFacts, HostInspector
from aptl.containment.launch_status import parse_launch_status
from aptl.containment.outcome import (
    Evidence,
    Outcome,
    classify,
    host_properties,
    refusal,
    setup_failure,
    stopped_before_launch,
)
from aptl.containment.policy import denied_environment_names, launcher_policy
from aptl.core.agent_errors import AgentExecutionError
from aptl.core.containment import (
    REPORT_SCHEMA,
    AppliedBounds,
    EngineIdentity,
    ExecutionReport,
    ExecutionRequest,
    HostIdentity,
    PropertyState,
    ReasonCode,
    WorkerRunner,
    WorkerRunnerFailure,
)
from aptl.utils.pathsafe import PathContainmentError, open_private_dir_contained_nofollow

_LAUNCHER = Path(__file__).with_name("_launcher.py")
_GROUP_OR_OTHER_WRITE = 0o022
_STATUS_BYTES = 65536
_HOST_PATH = {"PATH": "/usr/bin:/bin"}


def _require_private_root(state_root: Path) -> None:
    """Refuse a state root that another user can write or that is a link."""
    try:
        status = state_root.lstat()
    except OSError:
        raise ValueError("the containment state root does not exist") from None
    if not stat.S_ISDIR(status.st_mode) or status.st_uid != os.geteuid():
        raise ValueError("the containment state root must be a directory owned by the current user")
    if stat.S_IMODE(status.st_mode) & _GROUP_OR_OTHER_WRITE:
        raise ValueError("the containment state root must not be writable by group or other users")


def _drain(fd: int) -> bytes:
    """Read what a status descriptor holds now, without waiting for writers."""
    os.set_blocking(fd, False)
    data = b""
    try:
        while len(data) < _STATUS_BYTES and (chunk := os.read(fd, 4096)):
            data += chunk
    except BlockingIOError:
        pass
    finally:
        os.close(fd)
    return data


class _Channels:
    """The launcher and Bubblewrap status pipes of one run."""

    def __init__(self) -> None:
        self._fds: list[int] = []

    def open(self) -> None:
        for _ in range(2):
            self._fds.extend(os.pipe())

    @property
    def status_write(self) -> int:
        return self._fds[1]

    @property
    def json_write(self) -> int:
        return self._fds[3]

    def collect(self) -> tuple[bytes, bytes]:
        """Close the write ends, then read what each status pipe holds."""
        os.close(self._fds[1])
        os.close(self._fds[3])
        launch, bubblewrap = _drain(self._fds[0]), _drain(self._fds[2])
        self._fds.clear()
        return launch, bubblewrap

    def close(self) -> None:
        for fd in self._fds:
            os.close(fd)
        self._fds.clear()


def _write_private(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    with os.fdopen(os.open(path, flags, 0o600), "wb") as stream:
        stream.write(data)


class BubblewrapContainmentAdapter:
    """Run requests in the Bubblewrap engine, one sandbox per run."""

    def __init__(
        self,
        *,
        state_root: Path,
        runner: WorkerRunner,
        bubblewrap: Path = BUBBLEWRAP,
        host: HostInspector | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        # Bubblewrap starts in the run directory, so every bind source is absolute.
        state_root = state_root.absolute()
        _require_private_root(state_root)
        self._state_root = state_root
        self._runner = runner
        self._bubblewrap = bubblewrap
        self._clock = clock
        self._host = host or HostInspector(runner, bubblewrap, cwd=state_root, clock=clock)

    def execute(
        self, request: ExecutionRequest, *, cancel_event: Event | None = None
    ) -> ExecutionReport:
        """Run ``request``; every outcome, including refusal, is a report.

        One deadline covers the host checks, the setup, and the target.
        """
        run_id = secrets.token_hex(16)
        deadline = self._clock() + request.limits.deadline_seconds
        facts = self._host.observe(deadline=deadline, cancel_event=cancel_event)
        denied = denied_environment_names(request.env)
        properties = host_properties(facts, denied)
        stopped = stopped_before_launch(properties, deadline - self._clock(), cancel_event)
        if stopped is not None:
            return self._report(run_id, request, facts, stopped, None)
        if any(item.state is not PropertyState.DELIVERED for item in properties):
            return self._report(run_id, request, facts, refusal(properties, denied_names=denied), None)
        if request.input_dir is not None and not request.input_dir.is_dir():
            outcome = refusal(properties, ReasonCode.INPUT_UNAVAILABLE, "the input directory does not exist")
            return self._report(run_id, request, facts, outcome, None)
        run_dir = self._state_root / run_id
        channels = _Channels()
        try:
            layout = self._prepare(run_id, request)
            channels.open()
        except (OSError, PathContainmentError) as exc:
            channels.close()
            outcome = setup_failure(properties, f"setup resources failed: {type(exc).__name__}")
            return self._report(run_id, request, facts, outcome, run_dir if run_dir.exists() else None)
        argv = run_arguments(
            self._bubblewrap, layout, status_fd=channels.status_write, json_fd=channels.json_write,
            argv=request.argv,
        )
        # The last deadline check before the payload leaves this process.
        remaining = deadline - self._clock()
        stopped = stopped_before_launch(properties, remaining, cancel_event)
        if stopped is not None:
            channels.close()
            return self._report(run_id, request, facts, stopped, run_dir)
        outcome = classify(self._run(argv, request, layout, remaining, channels, cancel_event), cancel_event)
        return self._report(run_id, request, facts, outcome, run_dir)

    def _prepare(self, run_id: str, request: ExecutionRequest) -> SandboxLayout:
        """Create the owner-only run directory and write the launcher policy."""
        for relative in (run_id, f"{run_id}/output"):
            os.close(open_private_dir_contained_nofollow(self._state_root, Path(relative)))
        run_dir = self._state_root / run_id
        policy = run_dir / "policy.json"
        _write_private(policy, json.dumps(launcher_policy(request, run_dir / "output")).encode())
        return SandboxLayout(_LAUNCHER, policy, run_dir / "output", request.input_dir)

    def _run(
        self,
        argv: tuple[str, ...],
        request: ExecutionRequest,
        layout: SandboxLayout,
        remaining: float,
        channels: _Channels,
        cancel_event: Event | None,
    ) -> Evidence:
        result, failure = None, None
        try:
            result = self._runner.run(
                argv,
                env=dict(_HOST_PATH),
                cwd=layout.output_dir.parent,
                stdin=request.stdin,
                timeout_seconds=remaining,
                max_output_bytes=request.limits.max_output_bytes,
                cancel_event=cancel_event,
                pass_fds=(channels.status_write, channels.json_write),
            )
        except (AgentExecutionError, OSError) as exc:
            failure = exc
        launch, bubblewrap = channels.collect()
        return Evidence(
            launch=parse_launch_status(launch),
            bubblewrap=parse_status(bubblewrap),
            result=result,
            failure=failure if isinstance(failure, WorkerRunnerFailure) else None,
            error=failure,
        )

    def _report(
        self,
        run_id: str,
        request: ExecutionRequest,
        facts: HostFacts,
        outcome: Outcome,
        run_dir: Path | None,
    ) -> ExecutionReport:
        return ExecutionReport(
            schema_version=REPORT_SCHEMA,
            run_id=run_id,
            label=request.label,
            status=outcome.status,
            failure_origin=outcome.origin,
            reason=outcome.reason,
            detail=outcome.detail,
            contained=outcome.target is not None
            and all(item.state is PropertyState.DELIVERED for item in outcome.properties),
            properties=outcome.properties,
            target=outcome.target,
            engine=EngineIdentity(
                implementation="lilrae.containment.bubblewrap/v1",
                bubblewrap_version=facts.bubblewrap_version,
                landlock_abi=facts.landlock_abi,
                libseccomp_version=facts.libseccomp_version,
            ),
            host=HostIdentity(kernel_release=os.uname().release),
            bounds=AppliedBounds(
                deadline_seconds=request.limits.deadline_seconds,
                max_output_bytes=request.limits.max_output_bytes,
                cpu_seconds=request.limits.cpu_seconds,
                max_file_mb=request.limits.max_file_mb,
                address_space_mb=request.limits.address_space_mb,
            ),
            cleanup=outcome.cleanup,
            run_dir=run_dir,
        )
