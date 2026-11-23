"""Cancellation stops one owned child without cancelling its peer."""

import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from aptl.workbench.process import (
    AgentExecutionError,
    BoundedProcessError,
    BoundedProcessRunner,
)


def test_running_child_cancellation_preserves_peer(tmp_path):
    started = tmp_path / "started"
    cancel = threading.Event()
    script = (
        f"import pathlib,time; pathlib.Path({str(started)!r}).touch(); time.sleep(60)"
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        stopped = pool.submit(
            BoundedProcessRunner.run,
            (sys.executable, "-c", script),
            env={"PATH": os.defpath},
            cwd=tmp_path,
            stdin=b"",
            timeout_seconds=60,
            max_output_bytes=4096,
            cancel_event=cancel,
        )
        peer = pool.submit(
            BoundedProcessRunner.run,
            (sys.executable, "-c", "print('peer')"),
            env={"PATH": os.defpath},
            cwd=tmp_path,
            stdin=b"",
            timeout_seconds=30,
            max_output_bytes=4096,
        )
        # A filesystem handshake proves the child started before cancellation.
        for _ in range(300):
            if started.exists() or stopped.done():
                break
            cancel.wait(0.1)
        cancel.set()
        with pytest.raises(BoundedProcessError, match="cancelled") as raised:
            stopped.result(timeout=30)
        assert started.exists()
        assert raised.value.cleanup.residual == ()
        assert peer.result().stdout == b"peer\n"


def test_cancelled_invocation_never_launches_child(tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(AgentExecutionError, match="cancelled"):
        BoundedProcessRunner.run(
            ("/not/an/executable",),
            env={},
            cwd=tmp_path,
            stdin=b"",
            timeout_seconds=30,
            max_output_bytes=4096,
            cancel_event=cancel,
        )
