"""The shared containment wrapper around the pinned engine (ADR-068).

Each run gets a private directory and a new worker process. The worker imports
the engine; this process never does. The canonical bounded runner starts the
worker with an outer deadline, a report-size bound and cancellation, and
cleans up the worker's process group.
"""

import json
import os
import secrets
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from pydantic import ValidationError

from aptl.containment._worker_report import WorkerReport
from aptl.containment.engine import EngineInstallation
from aptl.core.agent_errors import AgentExecutionError
from aptl.core.containment import (
    REPORT_SCHEMA,
    AppliedBounds,
    CleanupObservation,
    ExecutionReport,
    ExecutionRequest,
    FailureOrigin,
    HostIdentity,
    PropertyObservation,
    PropertyState,
    ReasonCode,
    RunStatus,
    WorkerCleanup,
    WorkerRunner,
    WorkerRunnerFailure,
    profile_properties,
)
from aptl.utils.pathsafe import (
    open_private_dir_contained_nofollow,
    remove_tree_contained_nofollow,
)
from aptl.utils.strict_json import model_validate_json_strict

# Worker start-up, the engine probes and namespace setup happen before the
# target deadline starts. No measurement exists yet, so the allowance is wide;
# the engine enforces the target deadline itself.
SETUP_ALLOWANCE_SECONDS = 120.0
# The fork spawn backend's per-stream drain bound (_spawn._CAPTURE_CAP) at the
# pinned commit. It bounds the worker's memory while it captures output.
TRANSIENT_CAPTURE_BYTES_PER_STREAM = 64 * 1024 * 1024
_REPORT_OVERHEAD_BYTES = 1024 * 1024
_WORKER_SCRIPT = Path(__file__).with_name("_worker.py")
_WORKER_MESSAGE_SCHEMA = "lilrae.containment.worker-message/v1"
_WORKER_PATH = "/usr/bin:/bin"
_GROUP_OR_OTHER_WRITE = 0o022


@dataclass(frozen=True)
class _RunDirectory:
    """The private paths of one run; only ``output`` is granted to the target."""

    root: Path

    @property
    def output(self) -> Path:
        return self.root / "output"

    @property
    def worker(self) -> Path:
        return self.root / "worker"

    @property
    def log(self) -> Path:
        return self.root / "engine.log"

    def worker_environment(self) -> dict[str, str]:
        home = self.worker / "home"
        return {
            "PATH": _WORKER_PATH,
            "LANG": "C.UTF-8",
            "HOME": str(home),
            "TMPDIR": str(self.worker / "tmp"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_STATE_HOME": str(home / ".local" / "state"),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
        }


def _create_run_directory(state_root: Path, run_id: str) -> _RunDirectory:
    """Create owner-only directories without following links."""
    for relative in ("", "/output", "/worker", "/worker/home", "/worker/tmp"):
        os.close(open_private_dir_contained_nofollow(state_root, Path(run_id + relative)))
    return _RunDirectory(state_root / run_id)


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


def _report_limit(request: ExecutionRequest) -> int:
    """Base64 of the bounded output, plus the report and diagnostics."""
    return 4 * (request.limits.max_output_bytes // 3 + 2) + _REPORT_OVERHEAD_BYTES


def _cleanup(observed: WorkerCleanup | None) -> CleanupObservation | None:
    if observed is None:
        return None
    return CleanupObservation(residual=tuple(observed.residual), seconds=observed.seconds)


@dataclass(frozen=True)
class _Outcome:
    """The worker facts for one report, before identity and bounds are added."""

    status: RunStatus
    origin: FailureOrigin
    reason: ReasonCode | None = None
    detail: str | None = None
    worker: WorkerReport | None = None
    cleanup: CleanupObservation | None = None


class RaptorContainmentAdapter:
    """Run requests through the pinned engine, one isolated worker per run."""

    def __init__(
        self,
        *,
        engine: EngineInstallation,
        state_root: Path,
        runner: WorkerRunner,
        python: Path = Path(sys.executable),
    ) -> None:
        _require_private_root(state_root)
        self._engine = engine
        self._state_root = state_root
        self._runner = runner
        self._python = python
        self._snapshot: Path | None = None

    def execute(
        self, request: ExecutionRequest, *, cancel_event: Event | None = None
    ) -> ExecutionReport:
        """Run ``request``; every outcome, including refusal, is a report."""
        run_id = secrets.token_hex(16)
        if self._snapshot is None:
            verification = self._engine.prepare(self._state_root)
            if verification.snapshot is None:
                refusal = _Outcome(RunStatus.REFUSED, FailureOrigin.SETUP, verification.reason, verification.detail)
                return self._report(run_id, request, refusal, None)
            # The snapshot is read-only and owner-only under the private state
            # root, so later runs import the same verified bytes.
            self._snapshot = verification.snapshot
        if request.input_dir is not None and not request.input_dir.is_dir():
            refusal = _Outcome(
                RunStatus.REFUSED, FailureOrigin.SETUP, ReasonCode.INPUT_UNAVAILABLE,
                "the input directory does not exist",
            )
            return self._report(run_id, request, refusal, None)
        directory = _create_run_directory(self._state_root, run_id)
        try:
            outcome = self._run_worker(directory, request, self._snapshot, cancel_event)
        finally:
            remove_tree_contained_nofollow(directory.root, Path("worker"))
        return self._report(run_id, request, outcome, directory.root)

    def _run_worker(
        self,
        directory: _RunDirectory,
        request: ExecutionRequest,
        snapshot: Path,
        cancel_event: Event | None,
    ) -> _Outcome:
        message = {
            "schema_version": _WORKER_MESSAGE_SCHEMA,
            "engine_root": str(snapshot),
            "output_dir": str(directory.output),
            "log_path": str(directory.log),
            "request": request.model_dump(mode="json"),
        }
        try:
            result = self._runner.run(
                (str(self._python), "-I", "-S", "-B", str(_WORKER_SCRIPT)),
                env=directory.worker_environment(),
                cwd=directory.worker,
                stdin=json.dumps(message).encode("utf-8"),
                timeout_seconds=request.limits.deadline_seconds + SETUP_ALLOWANCE_SECONDS,
                max_output_bytes=_report_limit(request),
                cancel_event=cancel_event,
            )
        except AgentExecutionError as exc:
            return _runner_failure(exc, cancel_event)
        cleanup = _cleanup(result.cleanup)
        if result.returncode != 0:
            return _Outcome(
                RunStatus.WORKER_FAILED, FailureOrigin.SUPERVISOR, ReasonCode.WORKER_PROCESS_FAILED,
                f"the worker exited with status {result.returncode}", cleanup=cleanup,
            )
        try:
            worker = model_validate_json_strict(WorkerReport, result.stdout)
        except (ValueError, ValidationError):
            return _Outcome(
                RunStatus.WORKER_FAILED, FailureOrigin.SUPERVISOR, ReasonCode.WORKER_REPORT_INVALID,
                "the worker report is absent or invalid", cleanup=cleanup,
            )
        return _Outcome(
            worker.status, worker.failure_origin, worker.reason, worker.detail, worker, cleanup
        )

    def _report(
        self, run_id: str, request: ExecutionRequest, outcome: _Outcome, run_dir: Path | None
    ) -> ExecutionReport:
        worker = outcome.worker
        properties = worker.properties if worker is not None else tuple(
            PropertyObservation(property=item, state=PropertyState.UNKNOWN, basis="not observed")
            for item in profile_properties(request.profile)
        )
        target = worker.target if worker is not None else None
        contained = target is not None and all(
            item.state is PropertyState.DELIVERED for item in properties
        )
        return ExecutionReport(
            schema_version=REPORT_SCHEMA,
            run_id=run_id,
            label=request.label,
            status=outcome.status,
            failure_origin=outcome.origin,
            reason=outcome.reason,
            detail=outcome.detail,
            contained=contained,
            properties=properties,
            target=target,
            engine=self._engine.identity(worker.containment_tier if worker is not None else None),
            host=HostIdentity(kernel_release=os.uname().release),
            bounds=AppliedBounds(
                deadline_seconds=request.limits.deadline_seconds,
                max_output_bytes=request.limits.max_output_bytes,
                transient_capture_bytes_per_stream=TRANSIENT_CAPTURE_BYTES_PER_STREAM,
                cpu_seconds=request.limits.cpu_seconds,
                max_file_mb=request.limits.max_file_mb,
                address_space_mb=request.limits.address_space_mb,
            ),
            cleanup=outcome.cleanup,
            run_dir=run_dir,
        )


def _runner_failure(exc: AgentExecutionError, cancel_event: Event | None) -> _Outcome:
    """Translate a runner error; cancellation is the consumer's own request."""
    failure = exc if isinstance(exc, WorkerRunnerFailure) else None
    cleanup = _cleanup(failure.cleanup) if failure is not None else None
    if cancel_event is not None and cancel_event.is_set():
        return _Outcome(
            RunStatus.CANCELLED, FailureOrigin.SUPERVISOR, ReasonCode.CANCELLED,
            "the consumer cancelled the run", cleanup=cleanup,
        )
    reason = failure.reason if failure is not None else str(exc)
    return _Outcome(
        RunStatus.WORKER_FAILED, FailureOrigin.SUPERVISOR, ReasonCode.WORKER_PROCESS_FAILED,
        reason[:512], cleanup=cleanup,
    )
