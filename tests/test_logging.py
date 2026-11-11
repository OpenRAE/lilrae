"""Tests for the structured logging setup.

Tests our logging configuration logic, not the logging module itself.
"""

import logging

import pytest


class TestLoggingSetup:
    """Tests for logging configuration."""

    def test_setup_creates_aptl_logger(self):
        """setup_logging should configure the 'aptl' logger."""
        from aptl.utils.logging import setup_logging

        setup_logging()
        logger = logging.getLogger("aptl")
        assert logger.level <= logging.DEBUG
        assert len(logger.handlers) > 0

    def test_setup_respects_level_parameter(self):
        """setup_logging(level=WARNING) should set logger to WARNING."""
        from aptl.utils.logging import setup_logging

        setup_logging(level=logging.WARNING)
        logger = logging.getLogger("aptl")
        assert logger.level == logging.WARNING

    def test_get_logger_returns_child_logger(self):
        """get_logger('config') should return aptl.config logger."""
        from aptl.utils.logging import get_logger

        logger = get_logger("config")
        assert logger.name == "aptl.config"

    def test_setup_does_not_duplicate_handlers(self):
        """Calling setup_logging twice should not add duplicate handlers."""
        from aptl.utils.logging import setup_logging

        setup_logging()
        handler_count_1 = len(logging.getLogger("aptl").handlers)
        setup_logging()
        handler_count_2 = len(logging.getLogger("aptl").handlers)
        assert handler_count_2 == handler_count_1


def _invoke_with_stub_logs(monkeypatch, *flags: str):
    """Run ``aptl <flags> lab stop --json`` with a stop that logs at two levels."""
    from typer.testing import CliRunner

    from aptl.cli import lab
    from aptl.cli.main import app
    from aptl.core.lab import LabResult

    def stub_stop(**_kwargs):
        stub = logging.getLogger("aptl.lab")
        stub.info("stub info line")
        stub.warning("stub warning line")
        return LabResult(success=True)

    monkeypatch.setattr(lab, "stop_lab", stub_stop)
    return CliRunner().invoke(app, [*flags, "lab", "stop", "--json"])


class TestCliLogging:
    """A CLI run configures the aptl logger itself (#1323)."""

    @pytest.mark.parametrize(
        ("flags", "level"),
        [
            ((), logging.WARNING),
            (("--verbose",), logging.INFO),
            (("--verbose", "--verbose"), logging.DEBUG),
            (("--verbose",) * 3, logging.DEBUG),
        ],
    )
    def test_cli_run_installs_one_handler_at_the_selected_level(
        self, monkeypatch, flags, level
    ):
        result = _invoke_with_stub_logs(monkeypatch, *flags)

        assert result.exit_code == 0, result.output
        logger = logging.getLogger("aptl")
        [handler] = logger.handlers
        assert logger.level == level
        assert handler.level == level

    @pytest.mark.parametrize(
        ("flags", "info_shown"),
        [((), False), (("--verbose",), True)],
    )
    def test_log_lines_go_to_stderr_not_json_stdout(
        self, monkeypatch, flags, info_shown
    ):
        import json

        result = _invoke_with_stub_logs(monkeypatch, *flags)

        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["ok"] is True
        assert "stub" not in result.stdout
        assert "[WARNING] aptl.lab: stub warning line" in result.stderr
        assert ("[INFO] aptl.lab: stub info line" in result.stderr) is info_shown

    def test_help_states_the_default_level(self):
        from typer.testing import CliRunner

        from aptl.cli.main import app

        result = CliRunner().invoke(app, ["--help"], env={"COLUMNS": "200"})

        assert result.exit_code == 0
        assert "only warnings and errors are logged" in result.stdout

    def test_an_earlier_setup_still_logs_to_the_current_stderr(self, monkeypatch):
        """Importing ``aptl.api.main`` sets logging up before a CLI run does.

        The handler that setup made must write to the standard error of the
        run, not to the stream that was current when it was created.
        """
        from aptl.utils.logging import setup_logging

        setup_logging()
        result = _invoke_with_stub_logs(monkeypatch, "--verbose")

        [handler] = logging.getLogger("aptl").handlers
        assert handler.level == logging.INFO
        assert "[INFO] aptl.lab: stub info line" in result.stderr
