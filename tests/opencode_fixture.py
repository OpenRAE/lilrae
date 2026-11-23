"""Explicit pins and routes for synthetic OpenCode executables."""

import hashlib
from pathlib import Path
import subprocess
import sys

from aptl.core.opencode import OpenCodeBuild, OpenRouterRoute
from aptl.workbench.lilrae_opencode import OpenCodeOptions


def synthetic_options(*, executable, **kwargs):
    return OpenCodeOptions(
        executable=executable,
        build=OpenCodeBuild(
            version="1.19.5",
            executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        ),
        route=OpenRouterRoute(
            endpoint="https://openrouter.ai/api/v1", serving_provider="test-provider"
        ),
        **kwargs,
    )


def install_wheel(root: Path, *, source_root: Path | None = None) -> Path:
    """Install a candidate without dependencies or network into a separate tree."""
    repo = source_root or Path(__file__).resolve().parents[1]
    wheels = root / "wheels"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(wheels),
            str(repo),
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )
    installed = root / "installed"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--target",
            str(installed),
            str(next(wheels.glob("*.whl"))),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    return installed
