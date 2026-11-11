"""Structured logging setup for APTL CLI."""

import logging
import sys

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class _StderrHandler(logging.StreamHandler):
    """Write each record to ``sys.stderr`` as it is when the record is emitted.

    ``typer.echo(err=True)`` and ``logging.lastResort`` resolve standard error
    per call too, so log lines follow a caller that swaps it (a CLI test runner,
    ``contextlib.redirect_stderr``) instead of the stream current at setup.
    """

    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stderr
        super().emit(record)


def setup_logging(level: int = logging.DEBUG) -> None:
    """Configure the aptl root logger.

    Idempotent: calling multiple times will not add duplicate handlers.

    Args:
        level: Logging level for the aptl logger.
    """
    logger = logging.getLogger("aptl")
    logger.setLevel(level)

    # Avoid adding duplicate handlers on repeated calls
    if not logger.handlers:
        handler = _StderrHandler()
        handler.setLevel(level)
        formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    else:
        # Update existing handler levels
        logger.setLevel(level)
        for handler in logger.handlers:
            handler.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the aptl namespace.

    Args:
        name: Module name (e.g., 'config', 'lab').

    Returns:
        A logger named 'aptl.<name>'.
    """
    return logging.getLogger(f"aptl.{name}")
