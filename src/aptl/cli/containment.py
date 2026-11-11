"""The ``lilrae containment`` command: the CLI and standard-I/O seam (ADR-068)."""

import signal
import sys
from pathlib import Path
from threading import Event
from types import FrameType
from typing import Annotated

import typer
from pydantic import ValidationError

from aptl.containment import BubblewrapContainmentAdapter
from aptl.core.containment import MAX_REQUEST_BYTES, ExecutionRequest
from aptl.utils.strict_json import model_validate_json_strict
from aptl.workbench.process import BoundedProcessRunner

app = typer.Typer(help="Run one command in the shared containment wrapper.", no_args_is_help=True)


def _fail(message: str) -> typer.Exit:
    """Print ``message`` on standard error and return the usage-error exit."""
    typer.echo(message, err=True)
    return typer.Exit(2)


def _read_request() -> ExecutionRequest:
    """Read and validate at most one bounded, strict JSON request from standard input."""
    payload = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(payload) > MAX_REQUEST_BYTES:
        raise _fail(f"invalid containment request: exceeds {MAX_REQUEST_BYTES} bytes")
    try:
        return model_validate_json_strict(ExecutionRequest, payload)
    except ValidationError as exc:
        locations = sorted({".".join(str(part) for part in item["loc"]) for item in exc.errors()})
        raise _fail(f"invalid containment request: {', '.join(locations)}") from None
    except ValueError:
        raise _fail("invalid containment request: the document is not strict JSON") from None


@app.command("run")
def run_command(
    state_root: Annotated[Path, typer.Option("--state-root", help="Private directory for run directories.")],
) -> None:
    """Read one request on standard input; write one report on standard output."""
    request = _read_request()
    try:
        adapter = BubblewrapContainmentAdapter(state_root=state_root, runner=BoundedProcessRunner())
    except ValueError as exc:
        raise _fail(str(exc)) from None
    cancel = Event()

    def _cancel(_number: int, _frame: FrameType | None) -> None:
        """Cancel the run when the process receives SIGTERM."""
        cancel.set()

    previous = signal.signal(signal.SIGTERM, _cancel)
    try:
        report = adapter.execute(request, cancel_event=cancel)
    finally:
        signal.signal(signal.SIGTERM, previous)
    sys.stdout.write(report.model_dump_json() + "\n")
