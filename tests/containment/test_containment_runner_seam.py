"""The bounded runner seam that the containment adapter uses."""

import os
import sys
from pathlib import Path

import pytest

from aptl.core.agent_errors import BoundedStopReason
from aptl.core.bounded_process import ProcessRequest
from aptl.workbench import process


def test_the_runner_uses_the_core_process_request() -> None:
    assert process.ProcessRequest is ProcessRequest


def test_runner_reasons_are_the_core_vocabulary() -> None:
    assert process.REASON_TIMEOUT is BoundedStopReason.TIMEOUT
    assert process.REASON_CANCELLED is BoundedStopReason.CANCELLED
    assert process.REASON_OVERFLOW is BoundedStopReason.OVERFLOW
    assert process.REASON_RESIDUE is BoundedStopReason.RESIDUE
    assert BoundedStopReason.TIMEOUT == "agent request exceeded the configured timeout"


@pytest.mark.integration
def test_runner_passes_only_the_named_descriptors(tmp_path: Path) -> None:
    read_end, write_end = os.pipe()
    unnamed = os.open(tmp_path, os.O_RDONLY)
    os.set_inheritable(unnamed, True)
    script = (
        "import os, sys; fds = sorted(int(n) for n in os.listdir('/proc/self/fd'));"
        f"os.write({write_end}, b'ok'); print(' '.join(map(str, fds)))"
    )
    try:
        result = process.BoundedProcessRunner.run_observed(
            ProcessRequest(
                (sys.executable, "-I", "-c", script),
                env={"PATH": "/usr/bin:/bin"},
                cwd=tmp_path,
                stdin=b"",
                timeout_seconds=30,
                max_output_bytes=4096,
                pass_fds=(write_end,),
            )
        )
    finally:
        os.close(write_end)
        os.close(unnamed)
    seen = {int(item) for item in result.stdout.split()}
    assert os.read(read_end, 2) == b"ok"
    os.close(read_end)
    assert write_end in seen
    assert unnamed not in seen
