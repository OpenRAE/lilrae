#!/usr/bin/env python3
"""Design acceptance adapter for the Python test runner.

The adapter validates one named acceptance case at a time (ADR-064 design
checks). Run it manually once per acceptance criterion. The adapter reads one
JSON request on stdin and writes one JSON observation on stdout.

Request (stdin)::

    {"test_file": "tests/test_feature.py", "test_name": "test_rejects_empty_name"}

Observation (stdout)::

    {"test_name": "test_rejects_empty_name", "status": "failed", "matches": 1,
     "message": "assert ... "}

``status`` is one of ``failed``, ``passed``, ``missing``, ``skipped``, or
``broken``. ``matches`` is the count of collected cases with that exact name.
A valid red observation has ``status`` ``failed``, exactly one ``matches``, and
the real assertion message. The adapter runs pytest in the same environment as
``tools/run-targeted-tests.sh``.

Rules:

* The adapter exits zero when it reports a valid observation, including a
  failing test. It exits nonzero only when it cannot run or report.
* pytest output goes to stderr. stdout holds only the one JSON object.
* A missing import, a syntax error, a skipped case, or duplicate matches cannot
  establish an intended failing case.
* The adapter never invents an observation from a name or a source search.

Usage: this adapter reads stdin, so run it through the ``workflow.design``
``acceptance_command`` in ``.ground-control.yaml``.
"""

from __future__ import annotations

import json
import os
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

# The request limits mirror the Ground Control contract (domain/design).
_MAX_INPUT_BYTES = 16 * 1024
_MAX_TEST_FILE = 500
_MAX_TEST_NAME = 2000
_MAX_MESSAGE = 6000
_VALID_STATUS = frozenset({"failed", "passed", "missing", "skipped", "broken"})
# pytest reports these call-phase exceptions as a real assertion failure. Every
# other exception is broken test wiring, not a red acceptance result.
_FAILURE_EXCEPTIONS = frozenset({"AssertionError", "Failed", "XFailed"})
_CREDENTIAL = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[-_]?key|authorization|bearer)\b"
    r"\s*[=:]\s*\S+",
)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class AdapterError(Exception):
    """The adapter cannot run or report an observation."""


def read_request(stream: object) -> tuple[str, str]:
    """Read and validate the one JSON request on ``stream``."""
    raw = stream.read(_MAX_INPUT_BYTES + 1)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    if len(raw.encode("utf-8")) > _MAX_INPUT_BYTES:
        raise AdapterError("the acceptance request is too large")
    try:
        request = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as error:
        raise AdapterError("the acceptance request is not valid JSON") from error
    if not isinstance(request, dict):
        raise AdapterError("the acceptance request must be a JSON object")
    test_file = request.get("test_file")
    test_name = request.get("test_name")
    if not _is_text(test_file, _MAX_TEST_FILE) or not _is_text(test_name, _MAX_TEST_NAME):
        raise AdapterError("the request must name a test_file and an exact test_name")
    return test_file, test_name.strip()


def _is_text(value: object, limit: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def safe_test_path(root: Path, test_file: str) -> Path:
    """Return the real path of ``test_file`` inside ``root``, or raise."""
    parts = test_file.split("/")
    if (
        test_file.startswith("/")
        or "\\" in test_file
        or _CONTROL.search(test_file)
        or any(part in ("", ".", "..", ".git") for part in parts)
    ):
        raise AdapterError("the test_file path is not a safe repository path")
    path = root / test_file
    if path.is_symlink():
        raise AdapterError("the test_file path must not be a symlink")
    resolved = path.resolve()
    if resolved != path.absolute() or root not in resolved.parents:
        raise AdapterError("the test_file path must stay inside the repository")
    if not resolved.is_file():
        raise AdapterError("the test_file path is not a regular file")
    return resolved


class _Collector:
    """Collect pytest collection and run reports for the named case."""

    def __init__(self, test_name: str) -> None:
        self.test_name = test_name
        self.selected = 0
        self.collect_errors: list[str] = []
        self.phases: dict[str, dict[str, object]] = {}
        self.exceptions: dict[str, set[str]] = {}

    def pytest_collectreport(self, report: object) -> None:
        if getattr(report, "failed", False):
            self.collect_errors.append(_longrepr_text(report))

    def pytest_collection_modifyitems(self, config: object, items: list) -> None:
        matched = [item for item in items if item.name == self.test_name]
        self.selected = len(matched)
        items[:] = matched

    def pytest_exception_interact(self, node: object, call: object, report: object) -> None:
        info = getattr(call, "excinfo", None)
        name = getattr(getattr(info, "type", None), "__name__", "")
        if name:
            self.exceptions.setdefault(report.nodeid, set()).add(name)

    def pytest_runtest_logreport(self, report: object) -> None:
        self.phases.setdefault(report.nodeid, {})[report.when] = report


def _longrepr_text(report: object) -> str:
    longrepr = getattr(report, "longrepr", None)
    return "" if longrepr is None else str(longrepr)


def _single_case_status(collector: _Collector) -> tuple[str, str]:
    """Return the (status, message) of the one selected case."""
    nodeid, phases = next(iter(collector.phases.items()))
    setup = phases.get("setup")
    call = phases.get("call")
    if setup is not None and getattr(setup, "failed", False):
        return "broken", _longrepr_text(setup)
    if setup is not None and getattr(setup, "skipped", False):
        return "skipped", "The acceptance case was skipped during setup."
    if call is None:
        return "broken", "The acceptance case did not run to a result."
    if getattr(call, "skipped", False):
        return "skipped", "The acceptance case was skipped or expected to fail."
    if getattr(call, "passed", False):
        teardown = phases.get("teardown")
        if teardown is not None and getattr(teardown, "failed", False):
            return "broken", _longrepr_text(teardown)
        return "passed", ""
    exceptions = collector.exceptions.get(nodeid, set())
    if exceptions & _FAILURE_EXCEPTIONS:
        return "failed", _longrepr_text(call)
    return "broken", _longrepr_text(call)


def observe(collector: _Collector) -> tuple[str, int, str]:
    """Return the (status, matches, message) for the collected run."""
    if collector.selected == 0:
        if collector.collect_errors:
            return "broken", 0, "\n".join(collector.collect_errors)
        return "missing", 0, "No acceptance case with this exact name was collected."
    if collector.selected > 1:
        return (
            "broken",
            collector.selected,
            f"{collector.selected} acceptance cases share this exact name; "
            "the selection must be unique.",
        )
    status, message = _single_case_status(collector)
    return status, 1, message


def run_case(root: Path, test_file: str, test_name: str) -> dict[str, object]:
    """Run the one named case and return its observation mapping."""
    path = safe_test_path(root, test_file)
    collector = _Collector(test_name)
    arguments = [
        str(path),
        "-o",
        "addopts=",
        "-p",
        "no:cacheprovider",
        "-p",
        "no:randomly",
        "--no-header",
        "-q",
    ]
    # pytest writes its terminal output to sys.stdout; keep stdout clean for the
    # one JSON object by sending that output to stderr.
    with redirect_stdout(sys.stderr):
        try:
            pytest.main(arguments, plugins=[collector])
        except Exception as error:  # noqa: BLE001 - adapter failure, reported below
            raise AdapterError(f"pytest did not run: {error}") from error
    status, matches, message = observe(collector)
    if status not in _VALID_STATUS:
        raise AdapterError(f"the adapter produced an unknown status {status!r}")
    return {
        "test_name": test_name,
        "status": status,
        "matches": matches,
        "message": _clean_message(message),
    }


def _clean_message(message: str) -> str:
    redacted = _CREDENTIAL.sub(lambda match: f"{match.group(1)}=[redacted]", message)
    redacted = _CONTROL.sub(" ", redacted)
    if len(redacted) <= _MAX_MESSAGE:
        return redacted
    half = _MAX_MESSAGE // 2 - 2
    return f"{redacted[:half]}\n...\n{redacted[-half:]}"


def main(stdin: object, stdout: object, root: Path) -> int:
    try:
        test_file, test_name = read_request(stdin)
        observation = run_case(root, test_file, test_name)
    except AdapterError as error:
        print(f"design-acceptance: {error}", file=sys.stderr)
        return 1
    stdout.write(json.dumps(observation))
    stdout.write("\n")
    stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.stdin, sys.__stdout__, Path(os.getcwd())))
