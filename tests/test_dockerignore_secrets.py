"""Contract for the operator secrets that the root build context excludes (#1752).

Docker sends the build context to the daemon. The root ``.dockerignore``,
which ``lilrae lab init`` also installs, must keep the operator secrets of a
lab project out of each root-context build (ADR-029). The exclusions must not
remove a file that a Dockerfile copies.
"""

from __future__ import annotations

import fnmatch
import json
import shlex
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SECRET_PATHS = (
    ".env",
    ".env.local",
    ".aptl/session.json",
    "keys/aptl_lab_key",
    "config/soc_certs/lab-ca.key",
    "config/wazuh_indexer_ssl_certs/admin-key.pem",
    "config/lab-ssh/id_ed25519",
)
KEPT_PATHS = (".env.example",)


def _patterns() -> list[str]:
    lines = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def _excluded(path: str, patterns: list[str]) -> bool:
    """Apply the patterns in order; a later ``!`` pattern re-includes a path."""
    excluded = False
    for raw in patterns:
        negated = raw.startswith("!")
        pattern = raw[1:] if negated else raw
        pattern = pattern.rstrip("/")
        if fnmatch.fnmatchcase(path, pattern) or path.startswith(pattern + "/"):
            excluded = not negated
    return excluded


def _instructions(dockerfile: Path) -> list[str]:
    """Return the Dockerfile instructions with line continuations joined."""
    joined: list[str] = []
    current = ""
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not current and (not stripped or stripped.startswith("#")):
            continue
        if stripped.endswith("\\"):
            current += stripped[:-1] + " "
            continue
        joined.append(current + stripped)
        current = ""
    return joined


def _copy_sources(dockerfile: Path) -> list[str]:
    """Return the local sources of each COPY and ADD instruction."""
    sources: list[str] = []
    for instruction in _instructions(dockerfile):
        keyword, _, rest = instruction.partition(" ")
        if keyword.upper() not in {"COPY", "ADD"}:
            continue
        rest = rest.strip()
        if rest.startswith("["):
            args = json.loads(rest)
        else:
            args = shlex.split(rest)
        if any(arg.startswith("--from=") for arg in args):
            continue
        operands = [arg for arg in args if not arg.startswith("--")]
        sources.extend(source.removeprefix("./").rstrip("/") for source in operands[:-1])
    return sources


def _dockerfiles() -> list[Path]:
    tracked = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "*Dockerfile*"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.split()
    return [REPO_ROOT / name for name in tracked]


def test_root_build_context_excludes_operator_secrets() -> None:
    patterns = _patterns()

    assert [path for path in SECRET_PATHS if not _excluded(path, patterns)] == []
    assert [path for path in KEPT_PATHS if _excluded(path, patterns)] == []


def test_secret_exclusions_keep_every_copied_source() -> None:
    patterns = _patterns()
    dockerfiles = _dockerfiles()

    removed = [
        f"{dockerfile.relative_to(REPO_ROOT)}: {source}"
        for dockerfile in dockerfiles
        for source in _copy_sources(dockerfile)
        if _excluded(source, patterns)
    ]

    assert dockerfiles
    assert removed == []
