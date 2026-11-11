"""Non-blocking standard-input delivery and bounded output capture.

The bounded process runner in :mod:`aptl.workbench.process` serves one child's
three pipes through one selector, so that no pipe can block it past its
deadline. This module holds that pipe exchange.
"""

from __future__ import annotations

import contextlib
import os
import selectors
import struct
import subprocess
import time

POLL_SECONDS = 0.02
CHUNK_BYTES = 65536


class PipeExchange:
    """Deliver standard input and capture bounded output without blocking.

    Output streams are registered with their capture buffer as selector data;
    standard input is registered with ``None``.
    """

    def __init__(
        self,
        selector: selectors.BaseSelector,
        stdin: bytes,
        limit: int,
    ) -> None:
        self._selector = selector
        self._pending = memoryview(stdin)
        self._remaining = limit
        self._capturing = True
        self._process: subprocess.Popen[bytes] | None = None
        self.stdout = bytearray()
        self.stderr = bytearray()

    def attach(self, process: subprocess.Popen[bytes]) -> None:
        """Register the child's pipes in non-blocking mode."""

        self._process = process
        for stream, captured in (
            (process.stdout, self.stdout),
            (process.stderr, self.stderr),
        ):
            os.set_blocking(stream.fileno(), False)
            self._selector.register(stream, selectors.EVENT_READ, captured)
        if self._pending:
            os.set_blocking(process.stdin.fileno(), False)
            self._selector.register(process.stdin, selectors.EVENT_WRITE)
        else:
            self.close_input()

    def pump(self, timeout: float) -> bool:
        """Serve every ready pipe once; return False when output overflows."""

        for key, _events in self._selector.select(timeout):
            if key.data is None:
                self._send()
            elif not self._receive(key):
                return False
        return True

    def drain(self) -> bool:
        """Capture what the exited child left in the pipes; False on overflow.

        Reading stops at the bytes waiting now: everything the child wrote, and
        nothing a descendant writes later, so it cannot exhaust the budget.
        """

        for key in self._output_keys():
            if not self._take(key, _pending_bytes(key.fd)):
                return False
        return True

    def stop_capture(self) -> None:
        """Discard output from now on; it is no longer part of the result."""

        self._capturing = False

    def close_input(self) -> None:
        """Close the child's standard input if it is still open."""

        stdin = self._process.stdin if self._process is not None else None
        if stdin is None or stdin.closed:
            return
        self._pending = memoryview(b"")
        with contextlib.suppress(KeyError):
            self._selector.unregister(stdin)
        with contextlib.suppress(OSError):
            stdin.close()

    def release(self, until: float) -> bool:
        """Discard output until its holders close it; return whether one remains."""

        while self._outputs_open() and time.monotonic() < until:
            self.pump(POLL_SECONDS)
        held = self._outputs_open()
        # Snapshot first: unregistering changes the selector's map.
        registered = [key.fileobj for key in self._selector.get_map().values()]
        for stream in registered:
            self._selector.unregister(stream)
        if self._process is not None:
            for stream in (
                self._process.stdin,
                self._process.stdout,
                self._process.stderr,
            ):
                with contextlib.suppress(OSError):
                    stream.close()
        return held

    def _send(self) -> None:
        """Write the next chunk of standard input, tolerating early exit."""

        try:
            sent = os.write(self._process.stdin.fileno(), self._pending[:CHUNK_BYTES])
        except BlockingIOError:
            return
        except BrokenPipeError:
            self.close_input()
            return
        self._pending = self._pending[sent:]
        if not self._pending:
            self.close_input()

    def _receive(self, key: selectors.SelectorKey) -> bool:
        """Read one chunk; return False when it does not fit the budget."""

        try:
            chunk = os.read(key.fd, CHUNK_BYTES)
        except BlockingIOError:
            return True
        if not chunk:
            self._selector.unregister(key.fileobj)
            key.fileobj.close()
        elif self._capturing:
            return self._admit(key.data, chunk)
        return True

    def _take(self, key: selectors.SelectorKey, count: int) -> bool:
        """Admit up to ``count`` waiting bytes of one stream; False on overflow."""

        while count > 0:
            chunk = os.read(key.fd, min(count, CHUNK_BYTES))
            if not chunk:
                return True
            if not self._admit(key.data, chunk):
                return False
            count -= len(chunk)
        return True

    def _admit(self, captured: bytearray, chunk: bytes) -> bool:
        """Admit bytes within the remaining combined-output budget."""

        admitted = chunk[: self._remaining]
        self._remaining -= len(admitted)
        captured.extend(admitted)
        return len(admitted) == len(chunk)

    def _output_keys(self) -> list[selectors.SelectorKey]:
        """Return the output streams that are still registered."""

        return [
            key for key in self._selector.get_map().values() if key.data is not None
        ]

    def _outputs_open(self) -> bool:
        """Whether any output stream is still open at its other end."""

        return bool(self._output_keys())


def _pending_bytes(fd: int) -> int:
    """Return how many bytes the pipe at ``fd`` holds right now (FIONREAD)."""

    # POSIX-only like the runner, so imported here: this module imports anywhere.
    import fcntl
    import termios

    waiting = fcntl.ioctl(fd, termios.FIONREAD, struct.pack("i", 0))
    return struct.unpack("i", waiting)[0]
