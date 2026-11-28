"""Guard: web/Dockerfile.api CMD may only pass flags `aptl web serve` accepts.

Regression test for the crash loop where the CLI dropped `--workers` but the
container CMD kept passing `--workers 1`, so `aptl-web-api` exited with a
"No such option: --workers" usage error on every start. A real wheel/Trivy
build does not catch this (the image builds fine; it only fails at runtime), so
this pins the Dockerfile CMD to the actual CLI option surface.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from typer.main import get_command

from aptl.cli.web import app

REPO_ROOT = Path(__file__).resolve().parents[1]


def _dockerfile_cmd() -> tuple[list[str], list[str]]:
    """Return the root flags and the `web serve` flags of the CMD."""
    text = (REPO_ROOT / "web" / "Dockerfile.api").read_text(encoding="utf-8")
    match = re.search(r"^CMD\s+(\[.*\])\s*$", text, re.MULTILINE)
    assert match, "web/Dockerfile.api has no single-line JSON CMD array"
    argv = json.loads(match.group(1))
    assert argv[0] == "lilrae", argv
    web = argv.index("web")
    assert argv[web + 1] == "serve", argv
    serve_flags = [arg for arg in argv[web + 2 :] if arg.startswith("--")]
    return argv[1:web], serve_flags


def _long_options(command) -> set[str]:
    # Introspect the Click command the CLI actually builds, rather than scraping
    # --help text (whose rich rendering varies by terminal/env). This is the
    # authoritative option surface.
    return {
        opt
        for param in command.params
        for opt in param.opts
        if opt.startswith("--")
    }


def _valid_serve_flags() -> set[str]:
    command = get_command(app)
    return _long_options(getattr(command, "commands", {}).get("serve", command))


def test_web_api_dockerfile_cmd_uses_only_valid_root_flags() -> None:
    from aptl.cli.main import app as root_app

    root_flags, _ = _dockerfile_cmd()
    assert set(root_flags) <= _long_options(get_command(root_app)), root_flags


def test_web_api_container_logs_info_lines() -> None:
    """The API server keeps its INFO log lines; the CLI default is WARNING."""
    root_flags, _ = _dockerfile_cmd()
    assert root_flags == ["--verbose"]


def test_web_api_dockerfile_cmd_uses_only_valid_serve_flags() -> None:
    valid = _valid_serve_flags()
    _, flags = _dockerfile_cmd()
    assert flags, "expected at least one flag in the web-api CMD"
    for flag in flags:
        assert flag in valid, (
            f"web/Dockerfile.api CMD passes {flag}, which `aptl web serve` does "
            f"not accept (valid: {sorted(valid)})"
        )
