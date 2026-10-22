"""Write the participant desktop files as the participant (issue #1273).

The desktop shows declared SOC logins, so its files are private to the
participant account: ``~/.config/aptl/desktop`` is ``0700`` and every file is
``0600``, written atomically through :func:`aptl.utils.pathsafe.replace_private_nofollow`.
That helper refuses a parent the writer does not own, so a root lab start runs
:func:`main` in a child process as the participant and passes the files on
stdin. No file content enters argv, the environment, or lab state on disk.
"""

from __future__ import annotations

import base64
import html
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from aptl.utils.pathsafe import remove_contained_nofollow, replace_private_nofollow

DESKTOP_DIR = Path(".config") / "aptl" / "desktop"
CREDENTIALS_FILE = "credentials.html"
CONSOLES_FILE = "consoles.txt"
GUIDE_FILE = "guide.html"
_FILES = frozenset({CREDENTIALS_FILE, CONSOLES_FILE, GUIDE_FILE})


def render_credentials(logins: Sequence[tuple[str, str, str]]) -> bytes:
    """Render the declared logins as an escaped, script-free HTML page."""

    rows = "".join(
        "<tr><th>{}</th><td>{}</td><td>{}</td></tr>".format(
            *(html.escape(value, quote=True) for value in login)
        )
        for login in logins
    )
    page = (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'">'
        "<title>Lab logins</title></head><body><table>"
        "<tr><th>Console</th><th>Username</th><th>Password</th></tr>"
        f"{rows}</table></body></html>\n"
    )
    return page.encode("utf-8")


def render_consoles(urls: Sequence[str]) -> bytes:
    """Render one console URL per line for the session's browser."""

    return "".join(f"{url}\n" for url in urls).encode("utf-8")


def render_guide(data: bytes) -> bytes:
    """Show bounded UTF-8 guide text with no active markup or network loads."""

    text = html.escape(data.decode("utf-8"), quote=True)
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'">'
        "<title>Participant guide</title></head><body>"
        f"<pre>{text}</pre></body></html>\n"
    ).encode("utf-8")


def write_desktop_files(home: Path, files: Mapping[str, bytes]) -> None:
    """Make ``files`` the complete desktop surface under ``home``.

    Each supplied file is replaced as an owner-only file, and each desktop file
    not supplied is removed, so no earlier run's login, guide or console list
    survives. An empty mapping withdraws the whole surface.
    """

    if set(files) - _FILES:
        raise ValueError("unknown participant desktop file")
    # The marker coordinates the UI only. Every replacement or withdrawal
    # invalidates it until the management-owned handoff publishes readiness.
    remove_contained_nofollow(home, Path(".config/aptl/run-ready"))
    for name, data in files.items():
        replace_private_nofollow(home, DESKTOP_DIR / name, data)
    for name in sorted(_FILES - set(files)):
        if (home / DESKTOP_DIR).is_dir():
            remove_contained_nofollow(home, DESKTOP_DIR / name)
    # Retire the earlier raw-Markdown surface on upgrade as well.
    remove_contained_nofollow(home, DESKTOP_DIR / "guide.md")


def encoded_request(home: Path, files: Mapping[str, bytes]) -> str:
    """Return the stdin request :func:`main` reads."""

    return json.dumps(
        {
            "home": str(home),
            "files": {
                name: base64.b64encode(data).decode("ascii")
                for name, data in files.items()
            },
        }
    )


def main() -> int:
    """Write the files a parent lab start sent on stdin, as this account."""

    request = json.loads(sys.stdin.read())
    files = {
        str(name): base64.b64decode(value, validate=True)
        for name, value in dict(request["files"]).items()
    }
    write_desktop_files(Path(request["home"]), files)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
