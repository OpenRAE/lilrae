"""Shared Go-port process cases run against the unchanged Python release."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from aptl.workbench.process import (
    REASON_OVERFLOW,
    REASON_TIMEOUT,
    BoundedProcessError,
    BoundedProcessRunner,
)

CASES = json.loads(
    (Path(__file__).resolve().parents[1] / "conformance/testdata/process-cases.json")
    .read_text(encoding="utf-8")
)
CHILD = """
import os, sys, time
mode, *args = sys.argv[1:]
if mode == 'echo':
    sys.stdout.buffer.write(sys.stdin.buffer.read())
elif mode == 'args':
    sys.stdout.buffer.write(('\\n'.join(args) + '\\n').encode())
elif mode == 'output':
    sys.stdout.buffer.write(args[0].encode())
    sys.stderr.buffer.write(args[1].encode())
elif mode == 'exit':
    sys.exit(int(args[0]))
elif mode == 'sleep':
    time.sleep(60)
elif mode == 'duplex':
    sys.stdout.buffer.write(b'x' * (1 << 20))
    sys.stdout.buffer.flush()
    assert sys.stdin.buffer.read() == b'x' * (1 << 20)
"""


@pytest.mark.skipif(sys.platform == "win32", reason="Python reference is POSIX-only")
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_process_conformance(case: dict[str, object], tmp_path: Path) -> None:
    """Port cases define behavior, not the structure of either runner."""
    data = str(case.get("input", "")).encode()
    if "input_size" in case:
        data = b"x" * int(case["input_size"])
    kwargs = {
        "cwd": tmp_path,
        "env": {},
        "stdin": data,
        "timeout_seconds": int(case.get("timeout_ms", 10000)) / 1000,
        "max_output_bytes": int(case["limit"]),
    }
    argv = (sys.executable, "-c", CHILD, str(case["mode"]), *case.get("args", []))
    if "failure" in case:
        with pytest.raises(BoundedProcessError) as raised:
            BoundedProcessRunner.run(argv, **kwargs)
        reason = {"timeout": REASON_TIMEOUT, "overflow": REASON_OVERFLOW}
        assert raised.value.reason == reason[case["failure"]]
        assert not raised.value.cleanup.residual
        return
    result = BoundedProcessRunner.run(argv, **kwargs)
    expected = str(case.get("stdout", "")).encode()
    if "stdout_size" in case:
        expected = b"x" * int(case["stdout_size"])
    assert result.returncode == case["exit_code"]
    assert result.stdout == expected
    assert result.stderr == str(case["stderr"]).encode()
    assert not result.cleanup.residual
