"""Bound the two native Docker log streams before buffering their output."""

from collections.abc import Mapping, Sequence
from io import BufferedReader
import os
import signal
import subprocess
from queue import Empty, Full, Queue
from threading import Event, Thread
from time import monotonic


type PipeMessage = tuple[int, bytes | bool | None]


class LogCapture(subprocess.CompletedProcess[str]):
    """A completed native log read with explicit byte and time limit flags."""

    truncated: bool = False
    timed_out: bool = False


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
    buffers: list[bytearray],
    deadline: float,
    remaining: int,
) -> tuple[int, bool, bool]:
    """Retain accepted pipe data until both streams end or a read limit is reached."""
    ended = 0
    truncated, timed_out = False, False
    while ended < 2:
        wait = deadline - monotonic()
        if wait <= 0:
            timed_out = True
            break
        try:
            index, data = messages.get(timeout=min(wait, 0.1))
        except Empty:
            continue
        if data is False:
            truncated = True
            break
        if data is None:
            ended += 1
            continue
        accepted = min(len(data), remaining)
        buffers[index].extend(data[:accepted])
        remaining -= accepted
        if len(data) > accepted:
            truncated = True
            break
    return ended, truncated, timed_out


def capture_logs(
    command: list[str],
    *,
    cwd: str | os.PathLike[str] | None,
    env: Mapping[str, str] | None,
    timeout: float,
    max_bytes: int,
) -> LogCapture:
    """Read within a combined byte/time budget and reap the read-only command."""
    messages: Queue[PipeMessage] = Queue(maxsize=4)
    stopped = Event()
    buffers = [bytearray(), bytearray()]
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
    deadline = monotonic() + timeout
    try:
        ended, truncated, timed_out = _drain_messages(
            messages, buffers, deadline, max_bytes
        )
        if ended == 2:
            try:
                process.wait(timeout=max(0.001, deadline - monotonic()))
            except subprocess.TimeoutExpired:
                timed_out = True
    finally:
        _reap(process, readers, stopped)
    if truncated or timed_out:
        # Withhold a cut credential or record; only complete lines are safe.
        buffers = [data[: data.rfind(b"\n") + 1] for data in buffers]
    result = LogCapture(
        command,
        process.returncode,
        *(bytes(data).decode("utf-8", errors="replace") for data in buffers),
    )
    result.truncated, result.timed_out = truncated, timed_out
    return result
