#!/usr/bin/python3
"""Publish the participant desktop's hostnames into ``/etc/hosts`` (#1273).

Lab start resolves each hostname the participant browser must reach, and the
address it maps to, from the admitted SDL and the realized lab, then writes a
non-secret ``hosts.json``. This publisher is the one mechanism that applies it:
the appliance desktop handoff calls it, and the range host runs it from the
unit ``scripts/setup-rdp.sh`` installs. It never discovers an address itself.

It uses the Python standard library only, so a host's system interpreter can
run it as a file without LilRAE installed. It owns only the lines it marks: it
replaces them atomically, keeps every other line and the file's mode, and
refuses a link, an invalid address, or a hostname that could carry a second
entry onto its line.

Usage: ``participant_hosts.py <hosts.json> [<hosts file>]``
"""

from __future__ import annotations

import ipaddress
import fcntl
import json
import os
import re
import secrets
import stat
import sys
import pwd
from contextlib import contextmanager
from pathlib import Path

SCHEMA = "lilrae.participant-hosts/v1"
MARKER = "# lilrae-participant-desktop"
# Lines an earlier desktop handoff wrote under its own marker are owned too, so
# an upgrade removes them instead of leaving stale mappings behind.
_OWNED_MARKERS = (MARKER, "# aptl-seat-browser")
_HOSTNAME = re.compile(
    r"(?=.{1,253}\Z)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*"
)
_RESERVED = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "broadcasthost",
        "ip6-localhost",
        "ip6-loopback",
        "ip6-allnodes",
        "ip6-allrouters",
    }
)
_MAX_ENTRIES = 64


class HostsPublicationError(ValueError):
    """The hostname set or the hosts file is unsafe to publish."""


def validated_entries(document: object) -> list[tuple[str, str]]:
    """Return ``(address, hostname)`` pairs from a ``hosts.json`` document."""

    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise HostsPublicationError("participant hosts document is invalid")
    entries = document.get("entries")
    if not isinstance(entries, list) or len(entries) > _MAX_ENTRIES:
        raise HostsPublicationError("participant hosts entries are invalid")
    pairs: dict[str, str] = {}
    for entry in entries:
        address = entry.get("address") if isinstance(entry, dict) else None
        hostname = entry.get("hostname") if isinstance(entry, dict) else None
        if not isinstance(address, str) or not isinstance(hostname, str):
            raise HostsPublicationError("participant hosts entry is invalid")
        try:
            parsed_address = ipaddress.ip_address(address)
            if parsed_address.is_unspecified or parsed_address.is_multicast:
                raise ValueError
            parsed = str(parsed_address)
        except ValueError:
            raise HostsPublicationError(
                "participant hosts address is invalid"
            ) from None
        name = hostname.lower()
        if (
            not _HOSTNAME.fullmatch(name)
            or name in _RESERVED
            or name.endswith(".localhost")
        ):
            raise HostsPublicationError("participant hostname is invalid")
        if pairs.get(name, parsed) != parsed:
            raise HostsPublicationError("participant hostname maps to two addresses")
        pairs[name] = parsed
    return sorted((address, name) for name, address in pairs.items())


def rendered_hosts(existing: str, pairs: list[tuple[str, str]]) -> str:
    """Return ``existing`` with its owned lines replaced by ``pairs``."""

    kept = [
        line
        for line in existing.splitlines()
        if not any(line.rstrip().endswith(marker) for marker in _OWNED_MARKERS)
    ]
    proposed = {name: address for address, name in pairs}
    for line in kept:
        parts = line.split("#", 1)[0].lower().split()
        if len(parts) > 1 and any(
            name in proposed and proposed[name] != parts[0] for name in parts[1:]
        ):
            raise HostsPublicationError(
                "participant hostname conflicts with an unowned entry"
            )
    owned = [f"{address} {hostname} {MARKER}" for address, hostname in pairs]
    return "\n".join((*kept, *owned)) + "\n"


def publish(
    hosts_json: Path,
    hosts_file: Path = Path("/etc/hosts"),
    *,
    document_owner: int | None = None,
) -> None:
    """Apply ``hosts_json`` to ``hosts_file`` atomically, keeping its mode."""

    with _parent(hosts_json) as (directory, name):
        document, _metadata = _read_regular(
            directory, name, limit=128 * 1024, owner=document_owner
        )
    _replace_hosts(hosts_file, validated_entries(json.loads(document)))


def clear(hosts_file: Path = Path("/etc/hosts")) -> None:
    """Remove owned mappings without requiring a previous run's document."""

    _replace_hosts(hosts_file, [])


@contextmanager
def _parent(path: Path):
    """Walk every parent without following links; pin the resulting directory."""

    absolute = Path(os.path.abspath(path))
    descriptor = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        yield descriptor, absolute.name
    finally:
        os.close(descriptor)


def _read_regular(directory: int, name: str, *, limit: int, owner: int | None = None):
    """Read a bounded caller-owned file through its pinned parent."""

    # A FIFO must reach fstat without waiting for a writer at open().
    descriptor = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
    )
    with os.fdopen(descriptor, "r", encoding="utf-8") as source:
        metadata = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != (os.geteuid() if owner is None else owner)
            or metadata.st_mode & 0o022
            or metadata.st_size > limit
        ):
            raise HostsPublicationError("participant hosts file is unsafe")
        value = source.read(limit + 1)
        if len(value) > limit:
            raise HostsPublicationError("participant hosts file is too large")
        return value, metadata


def _replace_hosts(path: Path, pairs: list[tuple[str, str]]) -> None:
    """Serialize descriptor-relative atomic updates and preserve owner/mode."""

    with _parent(path) as (directory, name):
        lock = os.open(
            ".lilrae-hosts.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        try:
            metadata = os.fstat(lock)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid():
                raise HostsPublicationError("participant hosts lock is unsafe")
            fcntl.flock(lock, fcntl.LOCK_EX)
            existing, metadata = _read_regular(directory, name, limit=1024 * 1024)
            _replace_file(directory, name, rendered_hosts(existing, pairs), metadata)
        finally:
            os.close(lock)


def _replace_file(
    directory: int, name: str, value: str, metadata: os.stat_result
) -> None:
    """Publish through the held directory, refusing a changed destination."""

    temporary = f".hosts-{secrets.token_hex(12)}"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(value)
            output.flush()
            os.fchown(output.fileno(), metadata.st_uid, metadata.st_gid)
            os.fchmod(output.fileno(), stat.S_IMODE(metadata.st_mode))
            os.fsync(output.fileno())
        current = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise HostsPublicationError("hosts file changed during publication")
        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass


def main(argv: list[str]) -> int:
    """Publish one ``hosts.json``; print only a bounded reason on failure."""

    owner = None
    if len(argv) >= 3 and argv[1] == "--document-owner":
        try:
            owner = pwd.getpwnam(argv[2]).pw_uid
        except KeyError:
            print("participant hosts document owner is unavailable", file=sys.stderr)
            return 1
        argv = [argv[0], *argv[3:]]
    if len(argv) not in (2, 3):
        print(
            "usage: participant_hosts.py <hosts.json> [<hosts file>]", file=sys.stderr
        )
        return 2
    target = Path(argv[2]) if len(argv) == 3 else Path("/etc/hosts")
    try:
        if argv[1] == "--clear":
            clear(target)
        else:
            publish(Path(argv[1]), target, document_owner=owner)
    except (OSError, ValueError) as exc:
        reason = (
            str(exc) if isinstance(exc, HostsPublicationError) else type(exc).__name__
        )
        print(f"participant hosts not published: {reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
