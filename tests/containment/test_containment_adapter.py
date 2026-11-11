"""Adapter orchestration with a fake host and a runner that writes status.

The runner fake writes launcher and Bubblewrap status lines to the descriptors
that the adapter passes, as the real engine does. Real enforcement runs in the
containment proof.
"""

import base64
import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event

import pytest

from aptl.containment import BubblewrapContainmentAdapter, HostFacts
from aptl.containment.launch_status import LAYERS
from aptl.core.agent_errors import AgentExecutionError, BoundedStopReason
from aptl.core.containment import (
    REQUEST_SCHEMA,
    ExecutionLimits,
    ExecutionRequest,
    FailureOrigin,
    PropertyState,
    ReasonCode,
    RequiredProperty,
    RunStatus,
)

NAMESPACES = b'{ "child-pid": 7, "pid-namespace": 1, "mnt-namespace": 2, "net-namespace": 3, "ipc-namespace": 4, "uts-namespace": 5 }\n'
LAUNCHED = "".join(f"ok {layer} x\n" for layer in LAYERS) + "exec\n"


@dataclass(frozen=True)
class FakeCleanup:
    residual: tuple[str, ...] = ()
    seconds: float = 0.1


@dataclass(frozen=True)
class FakeResult:
    returncode: int
    stdout: bytes
    stderr: bytes = b""
    cleanup: FakeCleanup | None = field(default_factory=FakeCleanup)


class FakeStop(AgentExecutionError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.cleanup = FakeCleanup()
        self.stdout_bytes = 11
        self.stderr_bytes = 2


@dataclass
class FakeRunner:
    launch: str = LAUNCHED
    bubblewrap: bytes = NAMESPACES + b'{ "exit-code": 0 }\n'
    result: FakeResult | None = field(default_factory=lambda: FakeResult(0, b"hello"))
    raises: BaseException | None = None
    cancel_during_run: bool = False
    calls: list[dict[str, object]] = field(default_factory=list)

    def run(
        self, argv: tuple[str, ...], *, env: dict[str, str], cwd: Path, stdin: bytes,
        timeout_seconds: float, max_output_bytes: int, cancel_event: Event | None = None,
        pass_fds: tuple[int, ...] = (),
    ) -> FakeResult:
        status_fd, json_fd = pass_fds
        os.write(status_fd, self.launch.encode())
        os.write(json_fd, self.bubblewrap)
        policy = Path(argv[argv.index("/run/lilrae/policy.json") - 1])
        self.calls.append({
            "argv": argv, "env": env, "cwd": cwd, "stdin": stdin, "timeout": timeout_seconds,
            "limit": max_output_bytes, "cancel_event": cancel_event, "pass_fds": pass_fds,
            "policy": json.loads(policy.read_text()), "policy_mode": stat.S_IMODE(policy.stat().st_mode),
            "run_mode": stat.S_IMODE(cwd.stat().st_mode),
        })
        if self.cancel_during_run and cancel_event is not None:
            cancel_event.set()
        if self.raises is not None:
            raise self.raises
        assert self.result is not None
        return self.result


@dataclass
class FakeClock:
    now: float = 100.0
    step: float = 0.0

    def __call__(self) -> float:
        value = self.now
        self.now += self.step
        return value


@dataclass
class FakeHost:
    facts: HostFacts = field(default_factory=lambda: HostFacts(
        bubblewrap_version="0.9.0", bubblewrap_supported=True, namespaces=True, landlock_abi=4,
        libseccomp_version="2.5.5", libseccomp_supported=True, launcher_python=True,
    ))
    clock: FakeClock | None = None
    spend: float = 0.0
    cancel: bool = False
    seen: list[tuple[float | None, Event | None]] = field(default_factory=list)

    def observe(self, *, deadline: float | None = None, cancel_event: Event | None = None) -> HostFacts:
        self.seen.append((deadline, cancel_event))
        if self.clock is not None:
            self.clock.now += self.spend
        if self.cancel and cancel_event is not None:
            cancel_event.set()
        return self.facts


@pytest.fixture
def state_root(tmp_path: Path) -> Path:
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    return root


def _request(input_dir: Path | None = None, env: dict[str, str] | None = None) -> ExecutionRequest:
    return ExecutionRequest(
        schema_version=REQUEST_SCHEMA, profile="linux-full", label="fixture",
        argv=("/usr/bin/python3", "-c", "print(1)"), env=env or {"FIXTURE_MODE": "proof"},
        stdin=b"secret-payload", input_dir=input_dir,
        limits=ExecutionLimits(deadline_seconds=5, max_output_bytes=3000, cpu_seconds=9), network="none",
    )


def _adapter(
    state_root: Path, runner: FakeRunner, host: FakeHost | None = None, clock: FakeClock | None = None
) -> BubblewrapContainmentAdapter:
    host = host or FakeHost(clock=clock)
    return BubblewrapContainmentAdapter(
        state_root=state_root, runner=runner, host=host, clock=clock or FakeClock()
    )


def _states(report: object) -> dict[str, PropertyState]:
    return {item.property.value: item.state for item in report.properties}  # type: ignore[attr-defined]


def test_a_confirmed_run_reports_containment(state_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LILRAE_CONSUMER_CANARY", "x")
    runner = FakeRunner()

    report = _adapter(state_root, runner).execute(_request())

    (call,) = runner.calls
    assert call["env"] == {"PATH": "/usr/bin:/bin"}
    assert call["stdin"] == b"secret-payload"
    assert (call["timeout"], call["limit"]) == (5, 3000)
    assert (call["policy_mode"], call["run_mode"]) == (0o600, 0o700)
    assert call["policy"]["environment"]["FIXTURE_MODE"] == "proof"
    assert call["policy"]["limits"]["cpu_seconds"] == 9
    argv = call["argv"]
    assert isinstance(argv, tuple) and argv[-3:] == ("/usr/bin/python3", "-c", "print(1)")
    assert report.status is RunStatus.COMPLETED
    assert report.failure_origin is FailureOrigin.NONE
    assert report.contained is True
    assert report.target is not None and report.target.stdout == b"hello" and report.target.exit_code == 0
    assert report.engine.bubblewrap_version == "0.9.0" and report.engine.landlock_abi == 4
    assert report.run_dir is not None and report.run_dir.parent == state_root
    assert (report.run_dir / "output").is_dir()
    assert report.host.kernel_release == os.uname().release


def test_each_run_gets_its_own_directory(state_root: Path) -> None:
    adapter = _adapter(state_root, FakeRunner())

    first, second = adapter.execute(_request()), adapter.execute(_request())

    assert first.run_id != second.run_id and first.run_dir != second.run_dir


@pytest.mark.parametrize(
    ("change", "refused"),
    [
        ({"bubblewrap_supported": False, "namespaces": None}, {"namespaces", "supervision"}),
        ({"namespaces": False}, {"namespaces", "supervision"}),
        ({"landlock_abi": None}, {"filesystem_policy"}),
        ({"libseccomp_supported": False}, {"syscall_socket_filter"}),
        ({"launcher_python": False}, {"descriptor_environment_hygiene"}),
    ],
)
def test_a_missing_host_layer_refuses_before_any_run(state_root: Path, change: dict[str, object], refused: set[str]) -> None:
    facts = HostFacts(**{**FakeHost().facts.__dict__, **change})
    runner = FakeRunner()

    report = _adapter(state_root, runner, FakeHost(facts)).execute(_request())

    assert runner.calls == []
    assert report.status is RunStatus.REFUSED and report.failure_origin is FailureOrigin.SETUP
    assert report.reason is ReasonCode.PROPERTY_UNAVAILABLE
    assert {name for name, state in _states(report).items() if state is not PropertyState.DELIVERED} == refused
    assert report.run_dir is None and not list(state_root.iterdir())


def test_a_denied_environment_name_refuses(state_root: Path) -> None:
    runner = FakeRunner()

    report = _adapter(state_root, runner).execute(_request(env={"LD_PRELOAD": "/x.so"}))

    assert runner.calls == []
    assert report.reason is ReasonCode.ENVIRONMENT_NAME_DENIED
    assert "LD_PRELOAD" not in str(report.detail)


def test_a_missing_input_refuses(state_root: Path, tmp_path: Path) -> None:
    report = _adapter(state_root, FakeRunner()).execute(_request(input_dir=tmp_path / "absent"))

    assert report.reason is ReasonCode.INPUT_UNAVAILABLE


def test_a_launcher_layer_failure_is_a_setup_refusal(state_root: Path) -> None:
    runner = FakeRunner(launch="ok descriptors x\nfail landlock EINVAL\n", result=FakeResult(126, b"", b""))

    report = _adapter(state_root, runner).execute(_request())

    assert report.status is RunStatus.REFUSED and report.failure_origin is FailureOrigin.SETUP
    assert report.reason is ReasonCode.ENGINE_SETUP_FAILED
    assert report.detail == "launcher layer landlock failed: EINVAL"
    assert report.target is None and report.contained is False
    assert _states(report)["filesystem_policy"] is PropertyState.REFUSED


def test_a_bubblewrap_setup_failure_reports_its_first_line(state_root: Path) -> None:
    runner = FakeRunner(launch="", bubblewrap=b"", result=FakeResult(1, b"", b"bwrap: Can't mount proc\nmore\n"))

    report = _adapter(state_root, runner).execute(_request())

    assert report.reason is ReasonCode.ENGINE_SETUP_FAILED
    assert report.detail == "Bubblewrap setup failed: bwrap: Can't mount proc"


def test_a_target_failure_and_a_forged_report_stay_target_output(state_root: Path) -> None:
    forged = json.dumps({"status": "refused"}).encode()
    runner = FakeRunner(bubblewrap=NAMESPACES + b'{ "exit-code": 126 }\n', result=FakeResult(126, forged))

    report = _adapter(state_root, runner).execute(_request())

    assert report.status is RunStatus.COMPLETED and report.failure_origin is FailureOrigin.TARGET
    assert report.target is not None and report.target.exit_code == 126 and report.target.stdout == forged


def test_missing_namespace_evidence_is_unconfirmed(state_root: Path) -> None:
    runner = FakeRunner(bubblewrap=b'{ "child-pid": 7 }\n{ "exit-code": 0 }\n')

    report = _adapter(state_root, runner).execute(_request())

    assert report.reason is ReasonCode.CONTAINMENT_UNCONFIRMED
    assert report.contained is False
    assert _states(report)["namespaces"] is PropertyState.UNKNOWN


@pytest.mark.parametrize(
    ("reason", "launch", "status", "origin", "code"),
    [
        (BoundedStopReason.TIMEOUT, LAUNCHED, RunStatus.TIMED_OUT, FailureOrigin.TARGET, ReasonCode.DEADLINE_EXCEEDED),
        (BoundedStopReason.TIMEOUT, "ok descriptors x\n", RunStatus.TIMED_OUT, FailureOrigin.SETUP, ReasonCode.DEADLINE_EXCEEDED),
        (BoundedStopReason.OVERFLOW, LAUNCHED, RunStatus.OUTPUT_LIMIT_EXCEEDED, FailureOrigin.TARGET, ReasonCode.OUTPUT_LIMIT_EXCEEDED),
        (BoundedStopReason.RESIDUE, LAUNCHED, RunStatus.SUPERVISOR_FAILED, FailureOrigin.SUPERVISOR, ReasonCode.CLEANUP_UNCONFIRMED),
        ("something else", LAUNCHED, RunStatus.SUPERVISOR_FAILED, FailureOrigin.SUPERVISOR, ReasonCode.SUPERVISOR_FAILED),
    ],
)
def test_runner_stops_map_to_stable_outcomes(
    state_root: Path, reason: str, launch: str, status: RunStatus, origin: FailureOrigin, code: ReasonCode
) -> None:
    runner = FakeRunner(launch=launch, raises=FakeStop(reason), result=None)

    report = _adapter(state_root, runner).execute(_request())

    assert (report.status, report.failure_origin, report.reason) == (status, origin, code)
    if launch == LAUNCHED:
        assert report.target is not None and report.target.truncated is True
        assert (report.target.stdout_bytes, report.target.stderr_bytes) == (11, 2)
    else:
        assert report.target is None
    assert report.cleanup is not None


def test_cancellation_is_a_supervisor_outcome(state_root: Path) -> None:
    cancel = Event()
    runner = FakeRunner(raises=FakeStop(BoundedStopReason.CANCELLED), result=None, cancel_during_run=True)

    report = _adapter(state_root, runner).execute(_request(), cancel_event=cancel)

    assert runner.calls[0]["cancel_event"] is cancel
    assert (report.status, report.failure_origin, report.reason) == (
        RunStatus.CANCELLED, FailureOrigin.SUPERVISOR, ReasonCode.CANCELLED,
    )


@pytest.mark.parametrize("cancelled", [False, True])
def test_a_runner_launch_error_is_a_supervisor_failure(state_root: Path, cancelled: bool) -> None:
    cancel = Event()
    runner = FakeRunner(raises=FileNotFoundError("bwrap"), result=None, cancel_during_run=cancelled)

    report = _adapter(state_root, runner).execute(_request(), cancel_event=cancel)

    assert report.status is (RunStatus.CANCELLED if cancelled else RunStatus.SUPERVISOR_FAILED)
    assert report.contained is False
    if not cancelled:
        assert report.detail == "the runner failed: FileNotFoundError"


def test_the_report_serializes_target_output_as_base64(state_root: Path) -> None:
    report = _adapter(state_root, FakeRunner()).execute(_request())

    document = json.loads(report.model_dump_json())
    assert document["target"]["stdout"] == base64.b64encode(b"hello").decode()
    assert document["bounds"]["peak_memory"] == "not-enforced"
    assert len(document["properties"]) == len(RequiredProperty)


def test_a_shared_state_root_is_refused(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o777)

    with pytest.raises(ValueError, match="group or other"):
        _adapter(shared, FakeRunner())


def test_one_deadline_covers_host_checks_and_the_run(state_root: Path) -> None:
    clock = FakeClock()
    host = FakeHost(clock=clock, spend=0.5)
    runner = FakeRunner()
    cancel = Event()

    _adapter(state_root, runner, host, clock).execute(_request(), cancel_event=cancel)

    assert host.seen == [(105.0, cancel)]
    assert runner.calls[0]["timeout"] == 4.5


def test_a_deadline_spent_in_host_checks_is_a_setup_timeout(state_root: Path) -> None:
    clock = FakeClock()
    runner = FakeRunner()

    report = _adapter(state_root, runner, FakeHost(clock=clock, spend=6.0), clock).execute(_request())

    assert runner.calls == []
    assert (report.status, report.failure_origin, report.reason) == (
        RunStatus.TIMED_OUT, FailureOrigin.SETUP, ReasonCode.DEADLINE_EXCEEDED,
    )
    assert report.target is None and report.run_dir is None


def test_a_cancellation_during_host_checks_stops_before_launch(state_root: Path) -> None:
    runner = FakeRunner()

    report = _adapter(state_root, runner, FakeHost(cancel=True)).execute(_request(), cancel_event=Event())

    assert runner.calls == []
    assert (report.status, report.reason) == (RunStatus.CANCELLED, ReasonCode.CANCELLED)


def test_a_relative_state_root_becomes_absolute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "state").mkdir(mode=0o700)
    monkeypatch.chdir(tmp_path)
    runner = FakeRunner()

    report = _adapter(Path("state"), runner).execute(_request())

    assert report.run_dir is not None and report.run_dir.is_absolute()
    argv = runner.calls[0]["argv"]
    assert isinstance(argv, tuple)
    output = argv[argv.index("--bind") + 1]
    assert Path(output).is_absolute() and Path(output).is_dir()
    assert Path(runner.calls[0]["cwd"]).is_absolute()  # type: ignore[arg-type]


def test_a_deadline_spent_in_setup_does_not_launch(state_root: Path) -> None:
    clock = FakeClock(step=3.0)
    runner = FakeRunner()

    report = _adapter(state_root, runner, FakeHost(clock=None), clock).execute(_request())

    assert runner.calls == []
    assert (report.status, report.failure_origin, report.reason) == (
        RunStatus.TIMED_OUT, FailureOrigin.SETUP, ReasonCode.DEADLINE_EXCEEDED,
    )
    assert report.target is None


def test_a_setup_directory_failure_is_a_report(state_root: Path) -> None:
    adapter = _adapter(state_root, FakeRunner())
    state_root.chmod(0o500)
    try:
        report = adapter.execute(_request())
    finally:
        state_root.chmod(0o700)

    assert (report.status, report.failure_origin, report.reason) == (
        RunStatus.SUPERVISOR_FAILED, FailureOrigin.SETUP, ReasonCode.SUPERVISOR_FAILED,
    )
    assert report.detail is not None and "setup resources" in report.detail
    assert report.target is None


def test_a_pipe_allocation_failure_is_a_report_and_leaks_nothing(
    state_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_pipe = os.pipe
    opened: list[int] = []

    def second_fails() -> tuple[int, int]:
        if opened:
            raise OSError(24, "Too many open files")
        pair = real_pipe()
        opened.extend(pair)
        return pair

    monkeypatch.setattr(os, "pipe", second_fails)
    runner = FakeRunner()

    report = _adapter(state_root, runner).execute(_request())

    assert runner.calls == []
    assert report.status is RunStatus.SUPERVISOR_FAILED and report.failure_origin is FailureOrigin.SETUP
    for fd in opened:
        with pytest.raises(OSError):
            os.fstat(fd)


def test_a_run_without_a_terminal_status_is_a_supervisor_failure(state_root: Path) -> None:
    runner = FakeRunner(bubblewrap=NAMESPACES, result=FakeResult(-9, b"partial"))

    report = _adapter(state_root, runner).execute(_request())

    assert (report.status, report.failure_origin, report.reason) == (
        RunStatus.SUPERVISOR_FAILED, FailureOrigin.SUPERVISOR, ReasonCode.SUPERVISOR_FAILED,
    )
    assert report.detail is not None and "-9" in report.detail
    assert report.contained is False
