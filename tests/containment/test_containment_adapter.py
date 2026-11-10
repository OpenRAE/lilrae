"""Adapter orchestration with a fake runner; real enforcement runs in CI."""

import base64
import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event

import pytest

from aptl.containment import RaptorContainmentAdapter
from aptl.containment.engine import EngineInstallation, EnginePin, source_digest
from aptl.core.agent_errors import AgentExecutionError
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


@dataclass(frozen=True)
class FakeCleanup:
    residual: tuple[str, ...] = ()
    seconds: float = 0.25


@dataclass(frozen=True)
class FakeResult:
    returncode: int
    stdout: bytes
    stderr: bytes = b""
    cleanup: FakeCleanup | None = field(default_factory=FakeCleanup)


class FakeRunnerFailure(AgentExecutionError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.cleanup = FakeCleanup(residual=("process-group-cleanup-unconfirmed",))


@dataclass
class FakeRunner:
    result: FakeResult | None = None
    raises: BaseException | None = None
    calls: list[dict[str, object]] = field(default_factory=list)

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
    ) -> FakeResult:
        message = json.loads(stdin)
        self.calls.append(
            {
                "argv": argv, "env": env, "cwd": cwd, "message": message,
                "timeout": timeout_seconds, "limit": max_output_bytes,
                "cancel_event": cancel_event,
                "cwd_mode": stat.S_IMODE(cwd.stat().st_mode),
                "run_mode": stat.S_IMODE(Path(message["output_dir"]).parent.stat().st_mode),
            }
        )
        if self.raises is not None:
            raise self.raises
        assert self.result is not None
        return self.result


def _worker_report(**overrides: object) -> bytes:
    report: dict[str, object] = {
        "schema_version": "lilrae.containment.worker-report/v1",
        "status": "completed",
        "failure_origin": "none",
        "reason": None,
        "detail": None,
        "properties": [
            {"property": item.value, "state": "delivered", "basis": "probe"}
            for item in RequiredProperty
        ],
        "target": {
            "exit_code": 0, "signal": None,
            "stdout": base64.b64encode(b"hello").decode(), "stderr": "",
            "stdout_bytes": 5, "stderr_bytes": 0, "truncated": False,
        },
        "containment_tier": "mount-ns",
    }
    report.update(overrides)
    return json.dumps(report).encode()


@pytest.fixture
def engine(tmp_path: Path) -> EngineInstallation:
    root = tmp_path / "engine"
    (root / "core" / "sandbox").mkdir(parents=True)
    (root / "core" / "sandbox" / "__init__.py").write_text("")
    (root / "LICENSE").write_text("MIT License\n")
    pin = EnginePin(
        schema_version="lilrae.containment.engine-pin/v1",
        repository="https://github.com/OpenRAE/raptor",
        upstream="https://github.com/gadievron/raptor",
        commit="a" * 40,
        source_tree="core",
        source_digest=source_digest(root),
        license_file="LICENSE",
    )
    return EngineInstallation(root, pin)


@pytest.fixture
def state_root(tmp_path: Path) -> Path:
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    return root


def _request(input_dir: Path | None = None, **limits: object) -> ExecutionRequest:
    return ExecutionRequest(
        schema_version=REQUEST_SCHEMA,
        profile="linux-full",
        label="fixture",
        argv=("/usr/bin/python3", "-c", "print(1)"),
        env={"FIXTURE_MODE": "proof"},
        stdin=b"secret-payload",
        input_dir=input_dir,
        limits=ExecutionLimits(deadline_seconds=5, max_output_bytes=3000, **limits),
        network="none",
    )


def _adapter(engine: EngineInstallation, state_root: Path, runner: FakeRunner) -> RaptorContainmentAdapter:
    return RaptorContainmentAdapter(engine=engine, state_root=state_root, runner=runner)


def test_a_verified_run_starts_one_isolated_worker(
    engine: EngineInstallation, state_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LILRAE_CONSUMER_CANARY", "must-not-reach-the-worker")
    runner = FakeRunner(result=FakeResult(0, _worker_report()))

    report = _adapter(engine, state_root, runner).execute(_request())

    (call,) = runner.calls
    argv = call["argv"]
    assert isinstance(argv, tuple)
    assert argv[1:4] == ("-I", "-S", "-B")
    assert argv[4].endswith("containment/_worker.py")
    env = call["env"]
    assert isinstance(env, dict)
    assert "LILRAE_CONSUMER_CANARY" not in env
    assert set(env) == {
        "PATH", "LANG", "HOME", "TMPDIR",
        "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME",
    }
    assert call["timeout"] == 5 + 120
    assert call["limit"] >= 4 * 3000 // 3
    assert call["cwd_mode"] == 0o700
    assert call["run_mode"] == 0o700
    message = call["message"]
    assert isinstance(message, dict)
    snapshot = Path(message["engine_root"])
    assert snapshot.parent == state_root / "engine"
    assert (snapshot / "core" / "sandbox" / "__init__.py").is_file()
    assert base64.b64decode(message["request"]["stdin"]) == b"secret-payload"

    assert report.status is RunStatus.COMPLETED
    assert report.contained is True
    assert report.engine.containment_tier == "mount-ns"
    assert report.engine.commit == "a" * 40
    assert report.cleanup is not None
    assert report.cleanup.seconds == 0.25
    assert report.target is not None
    assert report.target.stdout == b"hello"
    assert report.bounds.peak_memory == "not-enforced"
    assert report.run_dir is not None
    assert report.run_dir.parent == state_root
    assert (report.run_dir / "output").is_dir()
    assert not (report.run_dir / "worker").exists()
    assert report.host.kernel_release == os.uname().release


def test_each_run_gets_its_own_directory(engine: EngineInstallation, state_root: Path) -> None:
    runner = FakeRunner(result=FakeResult(0, _worker_report()))
    adapter = _adapter(engine, state_root, runner)

    first = adapter.execute(_request())
    second = adapter.execute(_request())

    assert first.run_id != second.run_id
    assert first.run_dir != second.run_dir


def test_an_unverified_engine_refuses_without_a_worker(engine: EngineInstallation, state_root: Path) -> None:
    (engine.root / "core" / "sandbox" / "__init__.py").write_text("changed = True\n")
    runner = FakeRunner(result=FakeResult(0, _worker_report()))

    report = _adapter(engine, state_root, runner).execute(_request())

    assert runner.calls == []
    assert report.status is RunStatus.REFUSED
    assert report.failure_origin is FailureOrigin.SETUP
    assert report.reason is ReasonCode.ENGINE_UNVERIFIED
    assert report.run_dir is None
    assert {item.state for item in report.properties} == {PropertyState.UNKNOWN}


def test_a_missing_input_directory_refuses_without_a_worker(
    engine: EngineInstallation, state_root: Path, tmp_path: Path
) -> None:
    runner = FakeRunner(result=FakeResult(0, _worker_report()))

    report = _adapter(engine, state_root, runner).execute(_request(input_dir=tmp_path / "absent"))

    assert runner.calls == []
    assert report.reason is ReasonCode.INPUT_UNAVAILABLE


@pytest.mark.parametrize(
    "stdout",
    [
        b"",
        b"not json",
        _worker_report(status="cancelled"),
        _worker_report(properties=[]),
        _worker_report(extra=True),
        _worker_report() + b'{"second": 1}',
    ],
)
def test_an_invalid_worker_report_is_a_supervisor_failure(
    engine: EngineInstallation, state_root: Path, stdout: bytes
) -> None:
    runner = FakeRunner(result=FakeResult(0, stdout))

    report = _adapter(engine, state_root, runner).execute(_request())

    assert report.status is RunStatus.WORKER_FAILED
    assert report.failure_origin is FailureOrigin.SUPERVISOR
    assert report.reason is ReasonCode.WORKER_REPORT_INVALID
    assert report.contained is False
    assert report.target is None


def test_a_nonzero_worker_exit_is_a_supervisor_failure(
    engine: EngineInstallation, state_root: Path
) -> None:
    runner = FakeRunner(result=FakeResult(1, _worker_report(), b"Traceback"))

    report = _adapter(engine, state_root, runner).execute(_request())

    assert report.reason is ReasonCode.WORKER_PROCESS_FAILED
    assert report.detail is not None
    assert "Traceback" not in report.detail


def test_cancellation_reports_cancelled_with_cleanup(engine: EngineInstallation, state_root: Path) -> None:
    cancel = Event()
    cancel.set()
    runner = FakeRunner(raises=FakeRunnerFailure("agent request was cancelled"))

    report = _adapter(engine, state_root, runner).execute(_request(), cancel_event=cancel)

    assert runner.calls[0]["cancel_event"] is cancel
    assert report.status is RunStatus.CANCELLED
    assert report.failure_origin is FailureOrigin.SUPERVISOR
    assert report.cleanup is not None
    assert report.cleanup.residual == ("process-group-cleanup-unconfirmed",)
    assert report.contained is False


def test_a_runner_failure_without_cancellation_is_a_worker_failure(
    engine: EngineInstallation, state_root: Path
) -> None:
    runner = FakeRunner(raises=FakeRunnerFailure("agent request exceeded the configured timeout"))

    report = _adapter(engine, state_root, runner).execute(_request())

    assert report.status is RunStatus.WORKER_FAILED
    assert report.reason is ReasonCode.WORKER_PROCESS_FAILED
    assert report.detail == "agent request exceeded the configured timeout"


def test_a_worker_refusal_passes_through(engine: EngineInstallation, state_root: Path) -> None:
    properties = [
        {"property": item.value, "state": "refused" if item is RequiredProperty.NAMESPACES else "delivered", "basis": "probe"}
        for item in RequiredProperty
    ]
    stdout = _worker_report(
        status="refused", failure_origin="setup", reason="property_unavailable",
        detail="not delivered: namespaces", properties=properties, target=None,
        containment_tier=None,
    )
    runner = FakeRunner(result=FakeResult(0, stdout))

    report = _adapter(engine, state_root, runner).execute(_request())

    assert report.status is RunStatus.REFUSED
    assert report.reason is ReasonCode.PROPERTY_UNAVAILABLE
    assert report.contained is False
    assert report.target is None


def test_a_timeout_without_a_posture_record_is_not_contained(
    engine: EngineInstallation, state_root: Path
) -> None:
    properties = [
        {"property": item.value, "state": "delivered" if item is RequiredProperty.DESCRIPTOR_ENVIRONMENT_HYGIENE else "unknown", "basis": "probe"}
        for item in RequiredProperty
    ]
    stdout = _worker_report(
        status="timed_out", failure_origin="target", reason="deadline_exceeded",
        properties=properties, containment_tier=None,
    )
    runner = FakeRunner(result=FakeResult(0, stdout))

    report = _adapter(engine, state_root, runner).execute(_request(cpu_seconds=10))

    assert report.status is RunStatus.TIMED_OUT
    assert report.contained is False
    assert report.bounds.cpu_seconds == 10


def test_later_source_changes_never_reach_later_workers(
    engine: EngineInstallation, state_root: Path
) -> None:
    runner = FakeRunner(result=FakeResult(0, _worker_report()))
    adapter = _adapter(engine, state_root, runner)
    adapter.execute(_request())
    (engine.root / "core" / "sandbox" / "__init__.py").write_text("ATTACKER = True\n")

    adapter.execute(_request())
    fresh = _adapter(engine, state_root, runner).execute(_request())

    roots = {call["message"]["engine_root"] for call in runner.calls}  # type: ignore[index]
    assert len(roots) == 1
    (root,) = roots
    assert (Path(root) / "core" / "sandbox" / "__init__.py").read_text() == ""
    assert fresh.status is RunStatus.COMPLETED
