"""Stream the two output pipes of a native read command into spool files.

Output is never cut. A read fails as timed out only when neither pipe
delivers data for the progress timeout.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import BufferedReader
from typing import IO
import os
import signal
import subprocess
from queue import Empty, Full, Queue
from threading import Event, Thread
from time import monotonic


type PipeMessage = tuple[int, bytes | bool | None]


@dataclass(frozen=True)
class StreamExit:
    """How a streamed native read ended.

    ``failed_pipe`` is true when reading a pipe failed, so the spooled output
    may be incomplete.
    """

    returncode: int | None
    timed_out: bool
    failed_pipe: bool


def _send(messages: Queue[PipeMessage], stopped: Event, item: PipeMessage) -> None:
    """Deliver one reader event while collection remains active."""
    while not stopped.is_set():
        try:
            messages.put(item, timeout=0.05)
            return
        except Full:
            pass


def _read(
    stream: BufferedReader, index: int, messages: Queue[PipeMessage], stopped: Event
) -> None:
    """Drain one pipe into the bounded queue and signal its completion."""
    try:
        while not stopped.is_set():
            data = stream.read1(65536)
            if not data:
                break
            _send(messages, stopped, (index, data))
    except OSError, ValueError:
        _send(messages, stopped, (index, False))
    finally:
        _send(messages, stopped, (index, None))


def _reap(
    process: subprocess.Popen[bytes], readers: Sequence[Thread], stopped: Event
) -> None:
    """Stop the process group and join its pipe readers before returning."""
    stopped.set()
    if process.poll() is None or any(reader.is_alive() for reader in readers):
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
    process.wait(timeout=2)
    for reader in readers:
        reader.join(timeout=1)
    for stream, reader in zip((process.stdout, process.stderr), readers, strict=True):
        if not reader.is_alive():
            stream.close()


def _drain_messages(
    messages: Queue[PipeMessage],
    targets: Sequence[IO[bytes]],
    progress_timeout: float,
) -> tuple[int, bool, bool]:
    """Write pipe data to ``targets`` until both pipes end or progress stops."""
    ended = 0
    failed_pipe, timed_out = False, False
    last_progress = monotonic()
    while ended < 2:
        wait = last_progress + progress_timeout - monotonic()
        if wait <= 0:
            timed_out = True
            break
        try:
            index, data = messages.get(timeout=min(wait, 0.1))
        except Empty:
            continue
        last_progress = monotonic()
        if data is False:
            failed_pipe = True
            break
        if data is None:
            ended += 1
            continue
        targets[index].write(data)
    return ended, failed_pipe, timed_out


def stream_command(
    command: list[str],
    *,
    cwd: str | os.PathLike[str] | None,
    env: Mapping[str, str] | None,
    stdout: IO[bytes],
    stderr: IO[bytes],
    progress_timeout: float,
) -> StreamExit:
    """Run a read-only command, streaming its output, and reap it."""
    messages: Queue[PipeMessage] = Queue(maxsize=4)
    stopped = Event()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=os.name == "posix",
    )
    readers = [
        Thread(target=_read, args=(stream, index, messages, stopped), daemon=True)
        for index, stream in enumerate((process.stdout, process.stderr))
    ]
    for reader in readers:
        reader.start()
    try:
        ended, failed_pipe, timed_out = _drain_messages(
            messages, (stdout, stderr), progress_timeout
        )
        if ended == 2:
            try:
                process.wait(timeout=progress_timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
    finally:
        _reap(process, readers, stopped)
    stdout.flush()
    stderr.flush()
    return StreamExit(process.returncode, timed_out, failed_pipe)
