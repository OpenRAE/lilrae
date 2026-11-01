"""Stop a pytest run that names no test file.

``tools/run-targeted-tests.sh`` loads this plugin with
``-p require_test_targets``. pytest parses its own command line, so the value
of an option, such as the path after ``--ignore``, never counts as a target.
Without a test file, pytest collects the configured test paths: the full
suite, which only CI runs.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Reject the run unless each positional argument names a test file."""
    if config.args_source is not pytest.Config.ArgsSource.ARGS:
        raise pytest.UsageError("name the test files to run; the full suite runs only in CI")
    for arg in config.args:
        if not Path(config.invocation_params.dir, arg.split("::", 1)[0]).is_file():
            raise pytest.UsageError(f"{arg} names no test file; the full suite runs only in CI")
