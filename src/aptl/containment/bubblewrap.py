"""The Bubblewrap argument vector and status parser for one contained run."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

BUBBLEWRAP = Path("/usr/bin/bwrap")
LAUNCHER_PYTHON = "/usr/bin/python3"
_SANDBOX_RUN = "/run/lilrae"
LAUNCHER_IN_SANDBOX = f"{_SANDBOX_RUN}/launcher.py"
POLICY_IN_SANDBOX = f"{_SANDBOX_RUN}/policy.json"
# The input mounts outside every writable grant: a Landlock grant on a writable
# ancestor such as /tmp would otherwise also cover the input (for example a FIFO).
INPUT_IN_SANDBOX = f"{_SANDBOX_RUN}/input"
# Sonar S5443 is a false positive on the next line. The path names the fresh tmpfs that
# Bubblewrap mounts in the run's own mount namespace. No other user or process can reach it.
SANDBOX_TMP = "/tmp"  # NOSONAR(python:S5443) - private tmpfs of one sandbox, not the shared host /tmp
SANDBOX_HOME = f"{SANDBOX_TMP}/home"
REQUIRED_NAMESPACES = frozenset({
    "pid-namespace", "mnt-namespace", "net-namespace", "ipc-namespace", "uts-namespace",
})

_ISOLATION = (
    "--unshare-all", "--unshare-user", "--disable-userns", "--die-with-parent",
    "--new-session", "--cap-drop", "ALL", "--clearenv",
)
_SYSTEM_DIRS = ("/usr", "/bin", "/sbin", "/lib", "/lib64")
# The host /etc entries that dynamic loading, TLS, time, and user lookup need.
# Only public TLS material: never /etc/ssl/private.
_ETC_ENTRIES = (
    "/etc/ld.so.cache", "/etc/ld.so.conf", "/etc/ld.so.conf.d", "/etc/alternatives",
    "/etc/ssl/certs", "/etc/ssl/openssl.cnf", "/etc/ca-certificates", "/etc/localtime",
    "/etc/passwd", "/etc/group",
    "/etc/nsswitch.conf",
)
_STATUS_BYTES = 65536


def _system_view() -> list[str]:
    """Read-only system directories, a fresh procfs and /dev, and a private /tmp."""
    view: list[str] = []
    for path in _SYSTEM_DIRS:
        if os.path.islink(path):
            view += ["--symlink", os.readlink(path), path]
        elif os.path.isdir(path):
            view += ["--ro-bind", path, path]
    for path in _ETC_ENTRIES:
        if os.path.lexists(path):
            view += ["--ro-bind", path, path]
    return [*view, "--proc", "/proc", "--dev", "/dev", "--tmpfs", SANDBOX_TMP, "--dir", SANDBOX_HOME]


@dataclass(frozen=True)
class SandboxLayout:
    """The host paths that one run binds into its sandbox."""

    launcher: Path
    policy: Path
    output_dir: Path
    input_dir: Path | None


def run_arguments(
    bubblewrap: Path,
    layout: SandboxLayout,
    *,
    status_fd: int,
    json_fd: int,
    argv: tuple[str, ...],
) -> tuple[str, ...]:
    """Build the Bubblewrap command that starts the launcher and then the target."""
    grants: list[str] = []
    if layout.input_dir is not None:
        grants += ["--ro-bind", str(layout.input_dir), INPUT_IN_SANDBOX]
        if str(layout.input_dir) != INPUT_IN_SANDBOX:
            # Request paths under the host input path keep working.
            grants += ["--symlink", INPUT_IN_SANDBOX, str(layout.input_dir)]
    grants += [
        "--bind", str(layout.output_dir), str(layout.output_dir),
        "--ro-bind", str(layout.launcher), LAUNCHER_IN_SANDBOX,
        "--ro-bind", str(layout.policy), POLICY_IN_SANDBOX,
        "--chdir", str(layout.output_dir),
        "--json-status-fd", str(json_fd),
    ]
    launcher = (LAUNCHER_PYTHON, "-I", "-S", LAUNCHER_IN_SANDBOX, str(status_fd), POLICY_IN_SANDBOX)
    return (str(bubblewrap), *_ISOLATION, *_system_view(), *grants, "--", *launcher, "--", *argv)


def probe_arguments(bubblewrap: Path) -> tuple[str, ...]:
    """Build a command that proves Bubblewrap can create the namespaces here."""
    return (str(bubblewrap), *_ISOLATION, *_system_view(), "--", "/usr/bin/true")


@dataclass(frozen=True)
class BubblewrapStatus:
    """What Bubblewrap reported on its JSON status descriptor."""

    child_started: bool
    namespaces: frozenset[str]
    exit_code: int | None


def parse_status(data: bytes) -> BubblewrapStatus:
    """Read Bubblewrap's JSON lines; an unreadable line adds no evidence."""
    started, namespaces, exit_code = False, frozenset[str](), None
    for line in data[:_STATUS_BYTES].splitlines():
        try:
            document = json.loads(line)
        except ValueError:
            continue
        if not isinstance(document, dict):
            continue
        if isinstance(document.get("child-pid"), int):
            started = True
            namespaces = frozenset(
                key for key, value in document.items() if key.endswith("-namespace") and isinstance(value, int)
            )
        if isinstance(document.get("exit-code"), int):
            exit_code = document["exit-code"]
    return BubblewrapStatus(started, namespaces, exit_code)


def parse_version(output: bytes) -> tuple[int, ...] | None:
    """Read ``bubblewrap X.Y.Z`` from ``bwrap --version``."""
    fields = output.decode("ascii", errors="replace").split()
    if len(fields) != 2 or fields[0] != "bubblewrap":
        return None
    try:
        return tuple(int(part) for part in fields[1].split("."))
    except ValueError:
        return None
