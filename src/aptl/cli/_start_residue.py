"""Say what a failed lab start left in the project and how to recover (#952).

The start summary in ``aptl.cli.lab_render`` prints this block. It lives in its
own module so that one stays within the 500-line file limit.
"""

from __future__ import annotations

import typer

from aptl.core.lab_types import STOP_RECOVERY_ROUTES, StartResidue
from aptl.core.lifecycle_guard import stop_recovery_routes as stop_recovery_routes


def emit_start_residue(
    residue: StartResidue,
    routes: tuple[tuple[str, str], ...] = STOP_RECOVERY_ROUTES,
) -> None:
    """Print the residue a failed start left and the routes to recover from it."""

    counts = residue.describe()
    if residue.torn_down:
        volumes_command, volumes_effect = routes[-1]
        removed = (
            f"removed {counts}" if counts else "left no project containers or networks"
        )
        typer.echo(f"Teardown after the failed start {removed}; volumes were kept.")
        typer.echo(f"  `{volumes_command}` {volumes_effect}.")
        return
    # The post-teardown observation decides what is said: an unanswered one
    # confirms nothing, so it must not claim the teardown left anything.
    if counts is None:
        typer.echo(
            "The failed start may have left containers or networks in the "
            "project; they could not be observed."
        )
        teardown_note = (
            "--teardown-on-failure ran, but what remains could not be confirmed."
        )
    else:
        typer.echo(f"The failed start left {counts} in the project.")
        teardown_note = "--teardown-on-failure did not remove them."
    if residue.teardown_requested:
        typer.echo(f"  {teardown_note}")
    typer.echo("  To recover, run one of:")
    width = max(len(command) for command, _effect in routes)
    for command, effect in routes:
        typer.echo(f"    {command.ljust(width)}  {effect}")
