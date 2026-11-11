"""Main entry point for the LilRAE CLI (``lilrae``, formerly ``aptl``)."""

import logging
from typing import Optional

import typer

import aptl
from aptl.cli import (
    config,
    container,
    containment,
    doctor,
    experiment,
    kill,
    lab,
    mcp_access,
    runs,
    seat,
    web,
)
from aptl.cli._command_alias import warn_deprecated_command
from aptl.utils.logging import setup_logging

app = typer.Typer(
    name="lilrae",
    help="LilRAE CLI",
    no_args_is_help=True,
)

app.add_typer(lab.app, name="lab")
app.add_typer(config.app, name="config")
app.add_typer(container.app, name="container")
app.add_typer(runs.app, name="runs")
app.add_typer(web.app, name="web")
app.add_typer(kill.app, name="kill")
app.add_typer(experiment.app, name="experiment")
app.add_typer(seat.app, name="seat")
app.add_typer(mcp_access.app, name="mcp-access")
app.add_typer(containment.app, name="containment")
app.command("doctor")(doctor.doctor)


# The log level a CLI run installs, raised one step per --verbose. Warnings and
# errors print by default; what an operator needs at the default level is
# echoed, like the `[lab start]` progress lines (#1323).
_CLI_LOG_LEVELS = (logging.WARNING, logging.INFO, logging.DEBUG)


def _cli_log_level(verbose: int) -> int:
    """Return the ``aptl`` log level for a ``--verbose`` count."""
    return _CLI_LOG_LEVELS[min(verbose, len(_CLI_LOG_LEVELS) - 1)]


def _version_callback(value: bool) -> None:
    """Print the installed version and exit when ``--version`` is passed."""
    if value:
        typer.echo(f"lilrae {aptl.__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
    verbose: int = typer.Option(
        0,
        "--verbose",
        count=True,
        # A repeatable flag, not a value: hide the counter's int type and default.
        metavar="",
        show_default=False,
        help=(
            "Log more on standard error: once for INFO, twice for DEBUG. "
            "Without it, only warnings and errors are logged."
        ),
    ),
) -> None:
    """LilRAE CLI."""
    setup_logging(_cli_log_level(verbose))


def legacy_main() -> None:
    """Run the deprecated ``aptl`` alias of the ``lilrae`` command.

    The notice goes to stderr before Typer parses anything, so it also covers
    ``--help``, ``--version``, and usage errors. ``prog_name`` keeps help and
    usage stdout identical to ``lilrae``.
    """
    warn_deprecated_command("aptl", "lilrae")
    app(prog_name="lilrae")
