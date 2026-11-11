"""Integration proof of the shared containment wrapper (issue #1467).

These tests drive the real Bubblewrap engine and its launcher. Each test checks
its host precondition and fails, rather than skips, when it does not hold.
"""

import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from aptl.containment import BubblewrapContainmentAdapter
from aptl.core.containment import (
    REQUEST_SCHEMA,
    ExecutionLimits,
    ExecutionReport,
    ExecutionRequest,
    FailureOrigin,
    ProbeObservation,
    ProbeResult,
    ProbeVerdict,
    PropertyState,
    ReasonCode,
    RunStatus,
    classify_probe,
    parse_probe_output,
)
from aptl.workbench.process import BoundedProcessRunner

pytestmark = [pytest.mark.integration, pytest.mark.containment]

PAYLOAD = Path(__file__).with_name("fixtures") / "probe_payload.py"
SYSTEM_PYTHON = "/usr/bin/python3"
CANARY_NAME = "LILRAE_PROBE_CANARY"


def _require_full_host() -> None:
    assert Path(SYSTEM_PYTHON).is_file(), f"{SYSTEM_PYTHON} is required"
    probe = subprocess.run(
        ["/usr/bin/bwrap", "--unshare-all", "--unshare-user", "--disable-userns",
         "--ro-bind", "/", "/", "--", "/usr/bin/true"],
        capture_output=True, check=False, timeout=30,
    )
    assert probe.returncode == 0, f"Bubblewrap cannot create namespaces here: {probe.stderr!r}"


@pytest.fixture
def state_root(tmp_path: Path) -> Path:
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    return root


@pytest.fixture
def input_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "input"
    directory.mkdir()
    shutil.copy(PAYLOAD, directory / PAYLOAD.name)
    (directory / "data.txt").write_text("input-data")
    return directory


@pytest.fixture
def adapter(state_root: Path) -> BubblewrapContainmentAdapter:
    return BubblewrapContainmentAdapter(state_root=state_root, runner=BoundedProcessRunner())


def _request(
    argv: list[str],
    input_dir: Path | None,
    *,
    stdin: bytes = b"",
    env: dict[str, str] | None = None,
    deadline: float = 30,
    max_output: int = 65536,
) -> ExecutionRequest:
    return ExecutionRequest(
        schema_version=REQUEST_SCHEMA,
        profile="linux-full",
        label="proof",
        argv=tuple(argv),
        env=env or {},
        stdin=stdin,
        input_dir=input_dir,
        limits=ExecutionLimits(deadline_seconds=deadline, max_output_bytes=max_output),
        network="none",
    )


def _assert_contained(report: ExecutionReport) -> None:
    assert report.contained, report.model_dump_json(indent=2)
    assert {item.state for item in report.properties} == {PropertyState.DELIVERED}
    assert report.engine.landlock_abi is not None


def test_refusal_before_payload_without_bubblewrap(input_dir: Path, state_root: Path) -> None:
    adapter = BubblewrapContainmentAdapter(
        state_root=state_root, runner=BoundedProcessRunner(), bubblewrap=Path("/nonexistent/bwrap")
    )
    request = _request(
        ["/bin/sh", "-c", "cat > marker"],
        input_dir,
        stdin=b"stdin-canary-1467",
        env={"FIXTURE_TOKEN": "env-canary-1467"},
    )

    report = adapter.execute(request)

    assert report.status is RunStatus.REFUSED
    assert report.failure_origin is FailureOrigin.SETUP
    assert report.reason is ReasonCode.PROPERTY_UNAVAILABLE
    assert report.target is None
    assert report.contained is False
    assert report.run_dir is None
    states = {item.property.value: item.state for item in report.properties}
    assert states["namespaces"] is PropertyState.REFUSED
    assert states["supervision"] is PropertyState.REFUSED
    assert not list(state_root.iterdir())


def test_full_layer_set_runs_a_real_fixture(
    adapter: BubblewrapContainmentAdapter, input_dir: Path
) -> None:
    _require_full_host()
    script = (
        "import os, sys; data = sys.stdin.buffer.read();"
        f"open('result.txt', 'w').write(open('{input_dir}/data.txt').read() + str(len(data)));"
        "assert not os.path.exists('/etc/ssl/private'), 'host TLS private keys are visible';"
        "print('fixture-ok')"
    )

    report = adapter.execute(_request([SYSTEM_PYTHON, "-I", "-c", script], input_dir, stdin=b"12345"))

    _assert_contained(report)
    assert report.status is RunStatus.COMPLETED
    assert report.failure_origin is FailureOrigin.NONE
    assert report.target is not None
    assert report.target.stdout.strip() == b"fixture-ok"
    assert report.run_dir is not None
    assert (report.run_dir / "output" / "result.txt").read_text() == "input-data5"
    assert stat.S_IMODE((report.run_dir / "policy.json").stat().st_mode) == 0o600
    assert report.engine.bubblewrap_version is not None
    assert report.engine.libseccomp_version is not None


@dataclass
class _Host:
    """Host objects that probes try to reach."""

    canary_file: Path
    canary_dir: Path
    helper_pid: int
    tcp_port: int
    unix_path: str
    input_unix_path: str
    input_dgram_path: str
    input_fifo_path: str
    abstract_name: str
    canary: str
    input_dgram: socket.socket


@pytest.fixture
def host(tmp_path: Path, input_dir: Path) -> Iterator[_Host]:
    canary = f"canary-{os.getpid()}"
    canary_dir = tmp_path / "host"
    canary_dir.mkdir()
    canary_file = canary_dir / "secret.txt"
    canary_file.write_text(canary)
    helper = subprocess.Popen(["/bin/sleep", "300"], env={CANARY_NAME: canary})
    listeners = []
    try:
        tcp = socket.create_server(("127.0.0.1", 0))
        unix_path = str(canary_dir / "s")
        unix = socket.socket(socket.AF_UNIX)
        unix.bind(unix_path)
        # A live host socket inside the read-only input grant (review finding).
        input_unix_path = str(input_dir / "s")
        input_unix = socket.socket(socket.AF_UNIX)
        input_unix.bind(input_unix_path)
        input_dgram_path = str(input_dir / "d")
        input_dgram = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        input_dgram.bind(input_dgram_path)
        # A host FIFO with a live reader inside the read-only input grant.
        input_fifo_path = str(input_dir / "f")
        os.mkfifo(input_fifo_path)
        fifo_reader = os.open(input_fifo_path, os.O_RDONLY | os.O_NONBLOCK)
        abstract_name = f"lilrae-probe-{os.getpid()}"
        abstract = socket.socket(socket.AF_UNIX)
        abstract.bind("\0" + abstract_name)
        listeners = [tcp, unix, input_unix, input_dgram, abstract]
        for listener in (unix, input_unix, abstract):
            listener.listen()
        yield _Host(
            canary_file, canary_dir, helper.pid, tcp.getsockname()[1],
            unix_path, input_unix_path, input_dgram_path, input_fifo_path, abstract_name, canary,
            input_dgram,
        )
        os.close(fifo_reader)
    finally:
        helper.kill()
        helper.wait()
        for listener in listeners:
            listener.close()


def _probe_arguments(probe_id: str, host: _Host, input_dir: Path) -> list[str]:
    return {
        "host-file-read": [str(host.canary_file), host.canary],
        "host-file-write": [str(host.canary_dir)],
        "input-write": [str(input_dir)],
        "host-process-environ": [str(host.helper_pid), host.canary],
        "host-process-signal": [str(host.helper_pid)],
        "host-loopback-connect": [str(host.tcp_port)],
        "host-unix-socket-connect": [host.unix_path],
        "input-unix-socket-connect": [host.input_unix_path],
        "raw-domain-unix-connect": [host.input_unix_path],
        "input-unix-dgram-send": [host.input_dgram_path],
        "input-unix-raw-pair-send": [host.input_dgram_path],
        "input-fifo-write": [host.input_fifo_path],
        "abstract-unix-socket-connect": [host.abstract_name],
        "keyctl-syscall": [],
        "nested-user-namespace": [],
        "inherited-descriptor": [],
        "environment-canary": [CANARY_NAME],
    }[probe_id]


PAYLOAD_PROBES = [
    "host-file-read",
    "host-file-write",
    "input-write",
    "host-process-environ",
    "host-process-signal",
    "host-loopback-connect",
    "host-unix-socket-connect",
    "input-unix-socket-connect",
    "raw-domain-unix-connect",
    "input-unix-dgram-send",
    "input-unix-raw-pair-send",
    "input-fifo-write",
    "abstract-unix-socket-connect",
    "keyctl-syscall",
    "nested-user-namespace",
    "inherited-descriptor",
    "environment-canary",
]


DATAGRAM_PROBES = frozenset({"input-unix-dgram-send", "input-unix-raw-pair-send"})


def _received(listener: socket.socket) -> bool:
    """Drain the host datagram socket; report whether anything arrived."""
    listener.setblocking(False)
    arrived = False
    while True:
        try:
            listener.recv(65536)
        except BlockingIOError:
            return arrived
        arrived = True


def _control(probe_id: str, arguments: list[str], host: _Host, input_dir: Path) -> ProbeObservation:
    """Run the same payload without containment, with the authority it probes."""
    canary_file = host.canary_file.open("rb")
    try:
        completed = subprocess.run(
            [SYSTEM_PYTHON, "-I", str(input_dir / PAYLOAD.name), probe_id, *arguments],
            capture_output=True, timeout=30, check=False,
            env={**os.environ, CANARY_NAME: host.canary},
            pass_fds=(canary_file.fileno(),),
        )
    finally:
        canary_file.close()
    for leftover in input_dir.glob("escape-*"):
        leftover.unlink()
    for leftover in host.canary_dir.glob("escape-*"):
        leftover.unlink()
    return parse_probe_output(completed.stdout, probe_id)


@pytest.mark.parametrize("probe_id", PAYLOAD_PROBES)
def test_escape_probe_is_denied_with_a_working_control(
    probe_id: str,
    adapter: BubblewrapContainmentAdapter,
    host: _Host,
    input_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_full_host()
    monkeypatch.setenv(CANARY_NAME, host.canary)
    arguments = _probe_arguments(probe_id, host, input_dir)
    control = _control(probe_id, arguments, host, input_dir)
    datagram = probe_id in DATAGRAM_PROBES
    if datagram:
        assert _received(host.input_dgram), "the control datagram did not reach the host socket"
    inherited = host.canary_file.open("rb")
    os.set_inheritable(inherited.fileno(), True)
    try:
        report = adapter.execute(
            _request([SYSTEM_PYTHON, "-I", str(input_dir / PAYLOAD.name), probe_id, *arguments], input_dir)
        )
    finally:
        inherited.close()

    _assert_contained(report)
    assert report.target is not None
    contained = parse_probe_output(report.target.stdout, probe_id)
    assert classify_probe(control, contained) is ProbeVerdict.CONTAINED, (
        control, contained, report.target.stdout.decode(errors="replace")
    )
    assert list(host.canary_dir.glob("escape-*")) == []
    assert list(input_dir.glob("escape-*")) == []
    if datagram:
        assert not _received(host.input_dgram), "a contained datagram reached the host socket"


def _heartbeat_grows(path: Path, wait: float = 1.0) -> bool:
    before = path.stat().st_size if path.exists() else -1
    time.sleep(wait)
    return path.exists() and path.stat().st_size > before


def test_detached_descendant_ends_with_the_run(
    adapter: BubblewrapContainmentAdapter, input_dir: Path, tmp_path: Path
) -> None:
    _require_full_host()
    control_beat = tmp_path / "control-heartbeat"
    subprocess.run(
        [SYSTEM_PYTHON, "-I", str(PAYLOAD), "detached-descendant", str(control_beat), "3"],
        capture_output=True, timeout=30, check=True,
    )
    control = ProbeObservation(
        reached=True,
        result=ProbeResult.ALLOWED if _heartbeat_grows(control_beat) else ProbeResult.DENIED,
    )
    os.kill(int(Path(f"{control_beat}.pid").read_text()), signal.SIGKILL)

    report = adapter.execute(
        _request([SYSTEM_PYTHON, "-I", str(input_dir / PAYLOAD.name), "detached-descendant", "heartbeat", "20"], input_dir)
    )

    _assert_contained(report)
    assert report.run_dir is not None and report.target is not None
    beat = report.run_dir / "output" / "heartbeat"
    reached = parse_probe_output(report.target.stdout, "detached-descendant").reached and beat.exists()
    contained = ProbeObservation(
        reached=reached,
        result=ProbeResult.ALLOWED if _heartbeat_grows(beat) else ProbeResult.DENIED,
    )
    assert classify_probe(control, contained) is ProbeVerdict.CONTAINED


def test_deadline_ends_the_target(adapter: BubblewrapContainmentAdapter, input_dir: Path) -> None:
    _require_full_host()
    started = time.monotonic()

    report = adapter.execute(_request(["/bin/sleep", "60"], input_dir, deadline=1))

    assert time.monotonic() - started < 50
    assert report.status is RunStatus.TIMED_OUT
    assert report.failure_origin is FailureOrigin.TARGET
    assert report.reason is ReasonCode.DEADLINE_EXCEEDED


def _heartbeat_target(input_dir: Path) -> ExecutionRequest:
    script = (
        "import time\n"
        "while True:\n"
        "    open('heartbeat', 'a').write('.')\n"
        "    time.sleep(0.05)\n"
    )
    return _request([SYSTEM_PYTHON, "-I", "-c", script], input_dir, deadline=120)


def _wait_for(pattern: str, root: Path, timeout: float = 60) -> Path:
    ends = time.monotonic() + timeout
    while time.monotonic() < ends:
        found = sorted(root.glob(pattern))
        if found:
            return found[0]
        time.sleep(0.1)
    raise AssertionError(f"{pattern} did not appear under {root}")


def test_cancellation_ends_the_target(
    adapter: BubblewrapContainmentAdapter, input_dir: Path, state_root: Path
) -> None:
    _require_full_host()
    cancel = threading.Event()
    reports: list[ExecutionReport] = []
    worker = threading.Thread(
        target=lambda: reports.append(adapter.execute(_heartbeat_target(input_dir), cancel_event=cancel))
    )
    worker.start()
    beat = _wait_for("*/output/heartbeat", state_root)
    cancel.set()
    worker.join(timeout=60)

    assert not worker.is_alive()
    (report,) = reports
    assert report.status is RunStatus.CANCELLED
    assert report.failure_origin is FailureOrigin.SUPERVISOR
    assert not _heartbeat_grows(beat)


def test_aggregate_output_bound(adapter: BubblewrapContainmentAdapter, input_dir: Path) -> None:
    _require_full_host()
    script = "import sys; sys.stdout.write('x' * 1048576)"

    report = adapter.execute(_request([SYSTEM_PYTHON, "-I", "-c", script], input_dir, max_output=4096))

    assert report.status is RunStatus.OUTPUT_LIMIT_EXCEEDED
    assert report.target is not None
    assert report.target.stdout_bytes + report.target.stderr_bytes <= 4096
    assert report.target.truncated is True
    assert report.failure_origin is FailureOrigin.TARGET


def test_target_cannot_forge_a_setup_result(adapter: BubblewrapContainmentAdapter, input_dir: Path) -> None:
    _require_full_host()
    forged = '{"schema_version": "lilrae.containment.report/v1", "status": "refused"}'

    report = adapter.execute(_request(["/bin/sh", "-c", f"echo '{forged}'; exit 126"], input_dir))

    _assert_contained(report)
    assert report.status is RunStatus.COMPLETED
    assert report.failure_origin is FailureOrigin.TARGET
    assert report.target is not None
    assert report.target.exit_code == 126


def test_concurrent_runs_cannot_reach_each_other(
    adapter: BubblewrapContainmentAdapter, input_dir: Path, state_root: Path
) -> None:
    _require_full_host()
    cancel = threading.Event()
    reports: list[ExecutionReport] = []
    first = threading.Thread(
        target=lambda: reports.append(adapter.execute(_heartbeat_target(input_dir), cancel_event=cancel))
    )
    first.start()
    first_output = _wait_for("*/output/heartbeat", state_root).parent

    second = adapter.execute(
        _request([SYSTEM_PYTHON, "-I", str(input_dir / PAYLOAD.name), "host-file-write", str(first_output)], input_dir)
    )
    still_running = first.is_alive() and _heartbeat_grows(first_output / "heartbeat")
    cancel.set()
    first.join(timeout=60)

    _assert_contained(second)
    assert second.target is not None
    observation = parse_probe_output(second.target.stdout, "host-file-write")
    assert observation == ProbeObservation(reached=True, result=ProbeResult.DENIED)
    assert list(first_output.glob("escape-*")) == []
    assert still_running
    assert reports[0].status is RunStatus.CANCELLED


def test_cli_termination_signal_cancels_the_run(
    input_dir: Path, state_root: Path, tmp_path: Path
) -> None:
    _require_full_host()
    command = Path(sys.executable).with_name("lilrae")
    assert command.is_file(), "install the lilrae command into the test environment"
    request = tmp_path / "request.json"
    request.write_text(_heartbeat_target(input_dir).model_dump_json())
    with request.open("rb") as stdin:
        process = subprocess.Popen(
            [str(command), "containment", "run", "--state-root", str(state_root)],
            stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        beat = _wait_for("*/output/heartbeat", state_root)
        process.send_signal(signal.SIGTERM)
        stdout, _ = process.communicate(timeout=60)

    assert process.returncode == 0
    report = ExecutionReport.model_validate_json(stdout)
    assert report.status is RunStatus.CANCELLED
    assert not _heartbeat_grows(beat)
