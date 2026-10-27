"""CLI commands for configuration management.

Implements:
- ``lilrae config validate`` (CLI-002)
- ``lilrae config show`` (CLI-007)
"""

import json as _json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from aptl.cli._common import (
    PROJECT_DIR_HELP,
    exit_on_invalid_deployment_settings,
    resolve_config_for_cli,
)
from aptl.core.deployment import get_backend
from aptl.utils.logging import get_logger

log = get_logger("cli.config")

app = typer.Typer(help="Configuration management.")
console = Console()


_PROJECT_DIR_OPTION = typer.Option(
    Path("."),
    "--project-dir",
    "-d",
    help=PROJECT_DIR_HELP,
)


def _format_value(value: object) -> str:
    """Render a Pydantic field value for the show table."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


@app.command()
def show(
    project_dir: Path = _PROJECT_DIR_OPTION,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit the resolved configuration as machine-readable JSON.",
    ),
) -> None:
    """Display the resolved LilRAE configuration.

    Loads ``aptl.json`` via the same discovery rules as the rest of the
    CLI, validates it, and renders the resulting Pydantic model — defaults
    included.
    """
    config, _ = resolve_config_for_cli(project_dir)

    payload = config.model_dump(mode="json")
    if json_output:
        typer.echo(_json.dumps(payload, indent=2))
        return

    # Render each top-level field as its own table. ``model_dump`` keeps
    # the same field order as the Pydantic model declaration, so the
    # output ordering is stable across runs.
    for label, fields in payload.items():
        table = Table(title=label, show_header=True, header_style="bold cyan")
        table.add_column("Field")
        table.add_column("Value")
        if isinstance(fields, dict):
            for field_name, value in fields.items():
                table.add_row(field_name, _format_value(value))
        else:
            table.add_row(label, _format_value(fields))
        console.print(table)


@app.command()
def validate(
    project_dir: Path = _PROJECT_DIR_OPTION,
) -> None:
    """Validate the LilRAE configuration file.

    Loads ``aptl.json`` through the same path used by deployment
    operations and reports any JSON, type, or constraint errors. It also
    builds the configured deployment backend, without contacting it, so
    settings only the backend checks (an ssh-compose block without
    ``ssh_host``, for example) fail here as they would in ``lilrae lab start``.
    """
    config, project_root = resolve_config_for_cli(project_dir)
    with exit_on_invalid_deployment_settings():
        get_backend(config, project_root)
    typer.echo(f"{project_root / 'aptl.json'}: OK")


@app.command()
def migrate(
    project_dir: Path = _PROJECT_DIR_OPTION,
    scenario: str | None = typer.Option(
        None, "--scenario", help="Explicit scenario identity when the old file omitted it."
    ),
) -> None:
    """Convert historical topology settings and keep aptl.json.bak."""
    from aptl.core.config import find_config
    from aptl.core.lifecycle_guard import canonical_lifecycle_project_root
    from aptl.core.lilrae_config_migration import migrate_config
    from aptl.utils.pathsafe import PathContainmentError
    from aptl.core.lifecycle_guard import LifecycleLockUnavailableError
    from aptl.core.lifecycle_policy import LifecycleBusyError

    root = canonical_lifecycle_project_root(project_dir)
    path = find_config(root)
    if path is None:
        typer.echo("No aptl.json was found in the project.", err=True)
        raise typer.Exit(code=1)
    try:
        changed = migrate_config(path, scenario_identity=scenario)
    except (
        OSError, ValueError, PathContainmentError,
        LifecycleBusyError, LifecycleLockUnavailableError,
    ):
        typer.echo(
            "Configuration migration failed. Check the explicit scenario, "
            "legacy settings, retired profiles, backup file, and project lock.", err=True,
        )
        raise typer.Exit(code=1) from None
    typer.echo(
        "Migrated aptl.json; original saved as aptl.json.bak."
        if changed else "Configuration is already current."
    )
