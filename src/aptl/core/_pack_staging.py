"""Bounded, no-follow acquisition before env-packs validates portable content."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import BinaryIO

from aptl.utils.pathsafe import open_contained_nofollow, open_dir_contained_nofollow

# Acquisition budgets bound work before a manifest can be trusted. They are
# filesystem limits, not another definition of the upstream pack format.
MAX_MEMBERS = 4096
MAX_BYTES = 1024 * 1024 * 1024
MAX_DEPTH = 64


def copy_pack(source: Path, destination: Path) -> None:  # NOSONAR
    """Copy regular files privately, including legitimate installer hardlinks.

    Walk source components without following links and read each file through
    the same checked handle. Upstream validators then establish exact inventory
    and content identity. Installer bytecode is the sole inventory exclusion.
    """
    absolute = source.absolute()
    anchor = Path(absolute.anchor)
    relative = absolute.relative_to(anchor)
    pending = [Path()]
    members = total = 0
    while pending:
        directory = pending.pop()
        fd = open_dir_contained_nofollow(anchor, relative / directory)
        try:
            with os.scandir(fd) as entries:
                for entry in entries:
                    members += 1
                    if members > MAX_MEMBERS:  # NOSONAR
                        raise ValueError("source member budget exceeded")
                    item = directory / entry.name
                    mode = entry.stat(follow_symlinks=False).st_mode
                    if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):  # NOSONAR
                        raise ValueError("unsafe source member")
                    if entry.name == "__pycache__" or entry.name.endswith(  # NOSONAR
                        (".pyc", ".pyo")
                    ):
                        continue
                    if len(item.parts) > MAX_DEPTH:  # NOSONAR
                        raise ValueError("source depth budget exceeded")
                    if stat.S_ISDIR(mode):  # NOSONAR
                        pending.append(item)
                    else:
                        total += _copy_file(
                            anchor,
                            relative / item,
                            destination / item,
                            MAX_BYTES - total,
                        )
        finally:
            os.close(fd)


def _copy_file(anchor: Path, source: Path, target: Path, remaining: int) -> int:  # NOSONAR
    with open_contained_nofollow(anchor, source) as reader:
        info = os.fstat(reader.fileno())
        if info.st_size > remaining:
            raise ValueError("source byte budget exceeded")
        target = target.absolute()
        target_anchor = Path(target.anchor)
        parent_fd = open_dir_contained_nofollow(
            target_anchor, target.parent.relative_to(target_anchor), create=True,
        )
        try:
            fd = os.open(
                target.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=parent_fd,
            )
            with os.fdopen(fd, "wb") as writer:
                copied = _copy_bytes(reader, writer, remaining)
                os.fchmod(writer.fileno(), stat.S_IMODE(info.st_mode) & 0o777)
        finally:
            os.close(parent_fd)
    return copied


def _copy_bytes(reader: BinaryIO, writer: BinaryIO, remaining: int) -> int:
    """Stream bytes through the already checked handles within the source budget."""
    copied = 0
    while chunk := reader.read(min(1024 * 1024, remaining - copied + 1)):
        copied += len(chunk)
        if copied > remaining:
            raise ValueError("source byte budget exceeded")
        writer.write(chunk)
    return copied
