"""Main entry point for the LilRAE CLI (``lilrae``, formerly ``aptl``)."""

from typing import Optional

import typer

import aptl
from aptl.cli import (
    config,
    container,
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
app.command("doctor")(doctor.doctor)


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
) -> None:
    """LilRAE CLI."""


def legacy_main() -> None:
    """Run the deprecated ``aptl`` alias of the ``lilrae`` command.

    The notice goes to stderr before Typer parses anything, so it also covers
    ``--help``, ``--version``, and usage errors. ``prog_name`` keeps help and
    usage stdout identical to ``lilrae``.
    """
    warn_deprecated_command("aptl", "lilrae")
    app(prog_name="lilrae")
