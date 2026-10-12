"""Real-subprocess coverage for bounded workbench invocations (#963).

Every program here is a harmless Python child that sleeps, prints or fills a
pipe. Helpers end themselves after a minute, and each test kills whatever it
started, so a failing assertion cannot leave work running.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import selectors
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from aptl.workbench.process import (
    _REAP_SECONDS,
    _RELEASE_SECONDS,
    _SHUTDOWN_GRACE_SECONDS,
    _TERM_GRACE_SECONDS,
    BoundedProcessError,
    BoundedProcessRunner,
    ProcessResult,
    _PipeExchange,
)
from tests.test_participant_workbench_adapter import _poll_until_absent

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="process-group supervision is POSIX-only"
)

_REPO = Path(__file__).resolve().parents[1]
_ENVIRONMENT = {"PATH": "/usr/local/bin:/usr/bin:/bin"}
# Cleanup has three phases: SIGTERM grace, reap and stream release. The grace
# period is short when the child was stopped and long once it exited itself.
_CLEANUP_BOUND = _TERM_GRACE_SECONDS + _REAP_SECONDS + _RELEASE_SECONDS
_SHUTDOWN_BOUND = _SHUTDOWN_GRACE_SECONDS + _REAP_SECONDS + _RELEASE_SECONDS
# Still longer than the short grace period, so a test can tell the two apart.
_SHORTENED_SHUTDOWN_GRACE = 3.0
# Absorbs interpreter start-up and scheduling on loaded CI runners.
_SLACK = 3.0
# Long enough for the parent and its helper to start before the deadline.
_HANG_DEADLINE = 5.0
# Covers interpreter start-up and writing a few pipe buffers of output.
_INPUT_DEADLINE = 3.0
_RESULT = b'{"ok": true}\n'
# The OpenTelemetry OTLP exporter's default export timeout, which bounds the
# trace flush that starts the common MCP server's SIGTERM handler.
_OTLP_EXPORT_TIMEOUT_SECONDS = 10.0
# Never periodic, so a lost, repeated or reordered chunk changes the digest.
_PAYLOAD = hashlib.shake_256(b"#963 standard input").digest(1 << 20)

# Reads its standard input to end of file, as a provider CLI reads its prompt.
_READ_TO_END = (
    "import hashlib, sys; data = sys.stdin.buffer.read();"
    " print(len(data), hashlib.sha256(data).hexdigest())"
)

# Closes its standard input while most of the payload is still undelivered,
# then stays alive long enough for the runner's next write to hit the closed
# pipe, and fails.
_CLOSES_INPUT_EARLY = (
    "import os, sys, time; os.close(0); time.sleep(0.5);"
    " sys.stderr.write('input closed early'); sys.exit(3)"
)

# Ignores SIGTERM, and publishes its pid by rename only after it does.
_HELPER = """
import os, pathlib, signal, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
staged = pathlib.Path(sys.argv[1] + ".tmp")
staged.write_text(str(os.getpid()))
staged.replace(sys.argv[1])
time.sleep(60)
"""

# Like the helper, but records each SIGTERM in a marker file and keeps running,
# so a test can act while cleanup waits out its grace period.
_TERM_RECORDER = """
import os, pathlib, signal, sys, time
marker = pathlib.Path(sys.argv[1] + ".term")
signal.signal(signal.SIGTERM, lambda *_: marker.touch())
staged = pathlib.Path(sys.argv[1] + ".tmp")
staged.write_text(str(os.getpid()))
staged.replace(sys.argv[1])
time.sleep(60)
"""

# Shuts down slowly on SIGTERM, the way an MCP server awaits its SSH teardown,
# and records that its shutdown finished before it exits.
_SLOW_SHUTDOWN = """
import os, pathlib, signal, sys, time
def shut_down(*_):
    time.sleep(3)
    pathlib.Path(sys.argv[1] + ".done").touch()
    sys.exit(0)
signal.signal(signal.SIGTERM, shut_down)
staged = pathlib.Path(sys.argv[1] + ".tmp")
staged.write_text(str(os.getpid()))
staged.replace(sys.argv[1])
time.sleep(60)
"""

# The direct child: start one helper, wait until it is ready, then end as told.
# The helper inherits the child's standard streams either way.
_PARENT = """
import os, pathlib, subprocess, sys, time
helper, pid_file, session, ending = sys.argv[1:]
subprocess.Popen(
    [sys.executable, "-c", helper, pid_file],
    start_new_session=session == "detached",
)
limit = time.monotonic() + 30
while not pathlib.Path(pid_file).exists() and time.monotonic() < limit:
    time.sleep(0.01)
if ending == "flood":
    sys.stdout.buffer.write(b"x" * 65536)
    sys.stdout.flush()
if ending == "exit":
    sys.stderr.write(os.environ.get("CANARY", ""))
    print('{"ok": true}')
    sys.exit(0)
time.sleep(60)
"""


def _parent(
    pid_file: Path, session: str, ending: str, helper: str = _HELPER
) -> tuple[str, ...]:
    return (sys.executable, "-c", _PARENT, helper, str(pid_file), session, ending)


def _run(
    argv: tuple[str, ...],
    *,
    cwd: Path,
    timeout_seconds: float,
    stdin: bytes = b"",
    env: dict[str, str] | None = None,
    max_output_bytes: int = 1024,
) -> ProcessResult:
    """Run the real runner off-thread so that a broken bound fails, not hangs."""

    results: list[ProcessResult] = []
    errors: list[Exception] = []

    def invoke() -> None:
        try:
            results.append(
                BoundedProcessRunner.run(
                    argv,
                    env=env or dict(_ENVIRONMENT),
                    cwd=cwd,
                    stdin=stdin,
                    timeout_seconds=timeout_seconds,
                    max_output_bytes=max_output_bytes,
                )
            )
        except Exception as error:  # re-raised on the test thread below
            errors.append(error)

    worker = threading.Thread(target=invoke, daemon=True)
    worker.start()
    worker.join(timeout_seconds + _SHUTDOWN_BOUND + 30)
    assert not worker.is_alive(), "the runner outlived its deadline and cleanup"
    if errors:
        raise errors[0]
    return results[0]


def _outcome(
    argv: tuple[str, ...], *, cwd: Path, timeout_seconds: float
) -> ProcessResult | BoundedProcessError:
    try:
        return _run(argv, cwd=cwd, timeout_seconds=timeout_seconds)
    except BoundedProcessError as error:
        return error


def _wait_for(path: Path) -> bool:
    limit = time.monotonic() + 30
    while not path.exists() and time.monotonic() < limit:
        time.sleep(0.01)
    return path.exists()


def _published_pid(pid_file: Path) -> int:
    assert _wait_for(pid_file), "the helper never started"
    return int(pid_file.read_text(encoding="utf-8"))


def _confirm_gone(pid_file: Path) -> bool:
    """Whether the helper disappears; once it has, its pid is forgotten.

    A pid seen gone can be reused by an unrelated process, so the pid file is
    removed and ``_end_helper`` never signals that pid afterwards.
    """

    gone = _poll_until_absent(_published_pid(pid_file))
    if gone:
        pid_file.unlink()
    return gone


def _end_helper(pid_file: Path) -> None:
    """SIGKILL a helper that is still running; a no-op once it is gone."""

    with contextlib.suppress(OSError, ValueError):
        pid = int(pid_file.read_text(encoding="utf-8"))
        os.kill(pid, 0)
        os.kill(pid, signal.SIGKILL)


@pytest.fixture
def outside_service():
    """A long-lived service the invocation does not own, like a lab service."""

    service = subprocess.Popen(
        (sys.executable, "-c", "import time; time.sleep(60)"),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    yield service
    service.kill()
    service.wait()


@pytest.mark.parametrize(
    ("program", "stdout_bytes"),
    [
        pytest.param("import time; time.sleep(60)", 0, id="never-reads-input"),
        pytest.param(
            "import sys, time; sys.stdout.buffer.write(b'x' * 262144);"
            " sys.stdout.flush(); time.sleep(60)",
            262144,
            id="fills-output-pipe",
        ),
    ],
)
def test_deadline_covers_launch_input_and_output(
    program: str, stdout_bytes: int, tmp_path: Path
) -> None:
    """Undeliverable input and a full output pipe cannot stall the deadline.

    The regression: the deadline started only after a blocking write of the
    whole input, so a child that never read 8 MiB of it hung the runner
    forever.
    """

    started = time.monotonic()
    with pytest.raises(BoundedProcessError, match="timeout") as raised:
        _run(
            (sys.executable, "-c", program),
            cwd=tmp_path,
            stdin=b"i" * (8 << 20),
            timeout_seconds=_INPUT_DEADLINE,
            max_output_bytes=1 << 20,
        )
    elapsed = time.monotonic() - started

    cleanup = raised.value.cleanup
    assert raised.value.stdout_bytes == stdout_bytes
    assert cleanup.residual == ()
    assert cleanup.seconds < _CLEANUP_BOUND + _SLACK
    assert elapsed - cleanup.seconds < _INPUT_DEADLINE + _SLACK


def _digest(payload: bytes) -> bytes:
    """What ``_READ_TO_END`` prints for ``payload``."""

    return f"{len(payload)} {hashlib.sha256(payload).hexdigest()}\n".encode()


@pytest.mark.parametrize(
    ("program", "payload", "returncode", "stdout", "stderr"),
    [
        pytest.param(
            _READ_TO_END,
            _PAYLOAD[:13],
            0,
            _digest(_PAYLOAD[:13]),
            b"",
            id="13-bytes",
        ),
        pytest.param(
            _READ_TO_END,
            _PAYLOAD,
            0,
            _digest(_PAYLOAD),
            b"",
            id="1-mib",
        ),
        pytest.param(
            _CLOSES_INPUT_EARLY,
            _PAYLOAD,
            3,
            b"",
            b"input closed early",
            id="child-closes-input-early",
        ),
    ],
)
def test_input_arrives_whole_and_then_closes(
    program: str,
    payload: bytes,
    returncode: int,
    stdout: bytes,
    stderr: bytes,
    tmp_path: Path,
) -> None:
    """The prompt reaches the child intact, followed by end of file.

    Every provider turn sends its prompt on standard input, and a child that
    reads it to the end waits for the runner to close the pipe after the last
    byte. 1 MiB is more than a pipe buffer holds, so most of it can be written
    only as the child reads, and a write can be partial. A child that closes
    its input early still gets its exit status and error output returned, as
    ``dev`` returned them.
    """

    result = _run(
        (sys.executable, "-c", program),
        cwd=tmp_path,
        stdin=payload,
        timeout_seconds=30.0,
    )

    assert (result.returncode, result.stdout, result.stderr) == (
        returncode,
        stdout,
        stderr,
    )
    assert result.cleanup.residual == ()


@pytest.mark.parametrize(
    ("ending", "timeout_seconds", "failure", "grace", "bound"),
    [
        pytest.param(
            "exit",
            30.0,
            None,
            _SHORTENED_SHUTDOWN_GRACE,
            _SHORTENED_SHUTDOWN_GRACE + _REAP_SECONDS + _RELEASE_SECONDS,
            id="success",
        ),
        pytest.param(
            "flood",
            30.0,
            "output exceeded",
            _TERM_GRACE_SECONDS,
            _CLEANUP_BOUND,
            id="error",
        ),
        pytest.param(
            "hang",
            _HANG_DEADLINE,
            "timeout",
            _TERM_GRACE_SECONDS,
            _CLEANUP_BOUND,
            id="timeout",
        ),
    ],
)
def test_cleanup_kills_owned_helpers_and_spares_outside_services(
    ending: str,
    timeout_seconds: float,
    failure: str | None,
    grace: float,
    bound: float,
    tmp_path: Path,
    outside_service: subprocess.Popen[bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A SIGTERM-ignoring helper that outlives its parent never survives.

    It is killed once its grace period is over: the long one after the child
    exited on its own, the short one after the child was stopped at a limit.
    The long one is shortened here so that the test does not wait it out.
    The regression: success skipped group cleanup entirely, so the helper and
    the output streams it held outlived every successful request.
    """

    monkeypatch.setattr(
        "aptl.workbench.process._SHUTDOWN_GRACE_SECONDS", _SHORTENED_SHUTDOWN_GRACE
    )
    pid_file = tmp_path / "helper.pid"
    try:
        outcome = _outcome(
            _parent(pid_file, "owned", ending),
            cwd=tmp_path,
            timeout_seconds=timeout_seconds,
        )
        if failure is None:
            assert isinstance(outcome, ProcessResult)
            assert (outcome.returncode, outcome.stdout, outcome.stderr) == (
                0,
                _RESULT,
                b"",
            )
        else:
            assert isinstance(outcome, BoundedProcessError)
            assert failure in outcome.reason

        assert outcome.cleanup.residual == ()
        assert grace <= outcome.cleanup.seconds < bound + _SLACK
        assert _confirm_gone(pid_file), "a helper survived"
        assert outside_service.poll() is None, "cleanup reached a service"
    finally:
        _end_helper(pid_file)


@pytest.mark.parametrize(
    ("ending", "timeout_seconds", "finished"),
    [
        pytest.param("exit", 30.0, True, id="success"),
        pytest.param("hang", _HANG_DEADLINE, False, id="timeout"),
    ],
)
def test_helpers_finish_a_graceful_shutdown_only_after_the_child_exits(
    ending: str,
    timeout_seconds: float,
    finished: bool,
    tmp_path: Path,
) -> None:
    """After a success, helpers get time to shut down before SIGKILL.

    The helper takes 3 s to act on SIGTERM, as the common MCP server does
    while it closes its SSH sessions and the Kali capture wrapper flushes.
    After the child exits on its own, cleanup waits for it. After a timeout,
    the short grace period still applies, so the deadline does not stretch.
    The regression: cleanup sent SIGKILL 1 s after SIGTERM in both cases, so
    every successful turn cut off its MCP servers' teardown.
    """

    pid_file = tmp_path / "helper.pid"
    done = Path(f"{pid_file}.done")
    try:
        outcome = _outcome(
            _parent(pid_file, "owned", ending, helper=_SLOW_SHUTDOWN),
            cwd=tmp_path,
            timeout_seconds=timeout_seconds,
        )
        assert _confirm_gone(pid_file), "a helper survived"
        assert done.exists() is finished
        assert outcome.cleanup.residual == ()
        if finished:
            assert isinstance(outcome, ProcessResult)
            assert outcome.stdout == _RESULT
            assert outcome.cleanup.seconds < _SHUTDOWN_BOUND + _SLACK
        else:
            assert isinstance(outcome, BoundedProcessError)
            assert outcome.cleanup.seconds < _CLEANUP_BOUND + _SLACK
    finally:
        _end_helper(pid_file)


def test_shutdown_grace_covers_the_mcp_server_teardown_bounds() -> None:
    """The long grace period outlasts the common MCP server's SIGTERM path.

    The server flushes its traces, bounded by the OTLP exporter's default
    10 s timeout, then ``disconnectAll`` waits up to ``REMOTE_CLOSE_AWAIT``
    for the sessions' remote close and up to ``SESSION_CLOSE`` for the
    connections. If either SSH bound grows, this fails until the grace period
    is resized with it.
    """

    contracts = (_REPO / "mcp/aptl-mcp-common/src/ssh-contracts.ts").read_text(
        encoding="utf-8"
    )
    bounds = dict(
        re.findall(r"^\s*(REMOTE_CLOSE_AWAIT|SESSION_CLOSE): (\d+),", contracts, re.M)
    )

    assert set(bounds) == {"REMOTE_CLOSE_AWAIT", "SESSION_CLOSE"}
    ssh_seconds = sum(int(milliseconds) for milliseconds in bounds.values()) / 1000
    assert _OTLP_EXPORT_TIMEOUT_SECONDS + ssh_seconds < _SHUTDOWN_GRACE_SECONDS


def test_a_write_that_would_block_is_retried(tmp_path: Path) -> None:
    """Standard input survives a write that fails with EAGAIN.

    The runner treats the selector's readiness as a hint. If a write still
    fails with EAGAIN, which a real pipe does only when it has no room, the
    chunk stays pending and is offered again at the next readiness, so the
    child reads the whole prompt exactly once and the request succeeds. The
    stub refuses the first write of the prompt.
    """

    real_write = os.write
    refused: list[int] = []

    def refuse_the_first_input_write(fd: int, data: bytes) -> int:
        if not refused and bytes(data[:13]) == _PAYLOAD[:13]:
            refused.append(fd)
            raise BlockingIOError
        return real_write(fd, data)

    with mock.patch(
        "aptl.workbench.process.os.write", side_effect=refuse_the_first_input_write
    ):
        result = _run(
            (sys.executable, "-c", _READ_TO_END),
            cwd=tmp_path,
            stdin=_PAYLOAD,
            timeout_seconds=30.0,
        )

    assert refused, "no write was refused"
    assert (result.returncode, result.stdout) == (0, _digest(_PAYLOAD))
    assert result.cleanup.residual == ()


def test_capture_after_exit_takes_only_what_is_already_waiting() -> None:
    """A descendant that never stops writing cannot extend the result.

    The pipe holds what the exited child wrote, and ``os.read`` is stubbed to
    keep returning more, the way the pipe looks to its reader while a
    descendant floods it. The regression: capture went on after the exit for
    as long as the pipe stayed readable, so output that a descendant wrote
    after the exit was appended to the successful result until the budget
    ran out.
    """

    stdout_read, stdout_write = os.pipe()
    stderr_read, stderr_write = os.pipe()
    os.write(stdout_write, _RESULT)
    exited_child = SimpleNamespace(
        stdout=os.fdopen(stdout_read, "rb"),
        stderr=os.fdopen(stderr_read, "rb"),
        stdin=None,
    )
    try:
        with selectors.DefaultSelector() as selector:
            exchange = _PipeExchange(selector, b"", 1 << 20)
            exchange.attach(exited_child)
            with mock.patch(
                "aptl.workbench.process.os.read",
                side_effect=lambda _fd, size: b"x" * size,
            ):
                within_budget = exchange.drain()
    finally:
        for stream in (exited_child.stdout, exited_child.stderr):
            stream.close()
        os.close(stdout_write)
        os.close(stderr_write)

    assert within_budget, "the flood exhausted the output budget"
    assert (len(exchange.stdout), len(exchange.stderr)) == (len(_RESULT), 0)


def test_cleanup_signals_nothing_once_the_group_is_gone(tmp_path: Path) -> None:
    """A child that left nothing behind is never sent SIGTERM or SIGKILL.

    A group id that is free again can name a stranger's group, so cleanup
    signals only while the signal-0 probe still finds the group.
    """

    with mock.patch("aptl.workbench.process.os.killpg", wraps=os.killpg) as killpg:
        result = _run(
            (sys.executable, "-c", "print('{\"ok\": true}')"),
            cwd=tmp_path,
            timeout_seconds=30.0,
        )

    sent = {call.args[1] for call in killpg.call_args_list}
    assert result.stdout == _RESULT
    assert result.cleanup.residual == ()
    assert sent == {0}, "only the membership probe may reach the group"


def test_cancellation_still_cleans_up_and_notes_the_cleanup(
    tmp_path: Path,
    outside_service: subprocess.Popen[bytes],
) -> None:
    """A KeyboardInterrupt mid-request ends the invocation and propagates."""

    pid_file = tmp_path / "helper.pid"
    argv = _parent(pid_file, "owned", "hang")
    environment = dict(_ENVIRONMENT)

    def interrupt(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    def cancel_once_ready() -> None:
        if _wait_for(pid_file):
            os.kill(os.getpid(), signal.SIGUSR1)

    previous = signal.signal(signal.SIGUSR1, interrupt)
    try:
        threading.Thread(target=cancel_once_ready, daemon=True).start()
        with pytest.raises(KeyboardInterrupt) as raised:
            BoundedProcessRunner.run(
                argv,
                env=environment,
                cwd=tmp_path,
                stdin=b"",
                timeout_seconds=30.0,
                max_output_bytes=1024,
            )

        notes = "\n".join(getattr(raised.value, "__notes__", ()))
        assert "residual: none observed" in notes
        assert _confirm_gone(pid_file), "a helper survived"
        assert outside_service.poll() is None, "cleanup reached a service"
    finally:
        signal.signal(signal.SIGUSR1, previous)
        _end_helper(pid_file)


def test_a_second_interrupt_during_cleanup_still_kills_the_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pressing Ctrl-C again while cleanup waits out SIGTERM still escalates.

    The first interrupt cancels the request. The second lands in the grace
    period, after the helper has received SIGTERM and kept running; the grace
    period is lengthened so that the second interrupt cannot miss it. The
    regression: that interrupt abandoned cleanup between SIGTERM and SIGKILL,
    so the helper survived.
    """

    monkeypatch.setattr("aptl.workbench.process._TERM_GRACE_SECONDS", 30.0)
    pid_file = tmp_path / "helper.pid"
    argv = _parent(pid_file, "owned", "hang", helper=_TERM_RECORDER)
    environment = dict(_ENVIRONMENT)
    interrupts: list[float] = []

    def interrupt(_signum: int, _frame: object) -> None:
        interrupts.append(time.monotonic())
        raise KeyboardInterrupt

    def interrupt_twice() -> None:
        if _wait_for(pid_file):
            os.kill(os.getpid(), signal.SIGUSR1)
        if _wait_for(Path(f"{pid_file}.term")):
            os.kill(os.getpid(), signal.SIGUSR1)

    previous = signal.signal(signal.SIGUSR1, interrupt)
    try:
        threading.Thread(target=interrupt_twice, daemon=True).start()
        with pytest.raises(KeyboardInterrupt):
            BoundedProcessRunner.run(
                argv,
                env=environment,
                cwd=tmp_path,
                stdin=b"",
                timeout_seconds=30.0,
                max_output_bytes=1024,
            )

        assert len(interrupts) == 2, "the second interrupt missed cleanup"
        assert _confirm_gone(pid_file), "the helper survived interrupted cleanup"
    finally:
        signal.signal(signal.SIGUSR1, previous)
        _end_helper(pid_file)


def test_escaped_stream_holder_is_reported_without_secrets(tmp_path: Path) -> None:
    """A helper that left the process group is reported, not presumed gone.

    The regression: the runner waited one second per stream reader and then
    returned success while the helper still held the output streams.
    """

    pid_file = tmp_path / "helper.pid"
    argv = _parent(pid_file, "detached", "exit")
    canary = "canary-963-never-reported"
    try:
        with pytest.raises(BoundedProcessError) as raised:
            _run(
                argv,
                cwd=tmp_path,
                timeout_seconds=30.0,
                env={**_ENVIRONMENT, "CANARY": canary},
            )

        error = raised.value
        cleanup = error.cleanup
        assert cleanup.residual == ("output-streams-held",)
        assert cleanup.seconds < _CLEANUP_BOUND + _SLACK
        assert str(error) == (
            "agent process cleanup left residual processes; withheld captured "
            f"output (stdout {len(_RESULT)} bytes, stderr {len(canary)} bytes); "
            f"process group {cleanup.process_group} cleanup took "
            f"{cleanup.seconds:.2f}s; residual: output-streams-held"
        )
        helper = _published_pid(pid_file)
        assert not _poll_until_absent(helper, timeout=0.5), "outside the group"
    finally:
        _end_helper(pid_file)
