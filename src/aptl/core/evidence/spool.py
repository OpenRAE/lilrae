"""Spool files that let evidence sources stream content of any size.

A source writes native output to an anonymous spool file instead of memory.
The coordinator sets the spool directory to the run store, so spooled bytes
use the run-store disk and never a memory-backed temporary filesystem. A spool
file has no name and disappears when it is closed.

:class:`StreamedContent` hands spooled bytes to the coordinator as a
re-iterable chunk sequence. :class:`JsonArrayWriter` writes a JSON array of
records into a spool, streaming large string fields from other spools.
"""

from __future__ import annotations

import codecs
import itertools
import json
import tempfile
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import IO

_CHUNK = 1024 * 1024

#: Store-root directory for anonymous spool files; it never holds named files.
SPOOL_SUBDIR = ".evidence-spool"

_SPOOL_DIR: ContextVar[Path | None] = ContextVar("evidence_spool_dir", default=None)


@contextmanager
def spool_directory(path: Path) -> Iterator[None]:
    """Create nested spool files under ``path``."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    token = _SPOOL_DIR.set(path)
    try:
        yield
    finally:
        _SPOOL_DIR.reset(token)


def new_spool() -> IO[bytes]:
    """Return an anonymous read-write binary spool file."""
    return tempfile.TemporaryFile(dir=_SPOOL_DIR.get())


def iter_spool(spool: IO[bytes]) -> Iterator[bytes]:
    """Yield the whole content of ``spool`` from its start."""
    spool.seek(0)
    while chunk := spool.read(_CHUNK):
        yield chunk


def spool_size(spool: IO[bytes]) -> int:
    """Return the number of bytes in ``spool``."""
    spool.seek(0, 2)
    return spool.tell()


class StreamedContent:
    """Re-iterable source content backed by one spool file."""

    def __init__(self, spool: IO[bytes], *, event_count: int) -> None:
        self._spool = spool
        self.event_count = event_count

    def __iter__(self) -> Iterator[bytes]:
        return iter_spool(self._spool)

    def __bool__(self) -> bool:
        return spool_size(self._spool) > 0


def json_string_chunks(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """Encode a UTF-8 byte stream as one JSON string, chunk by chunk.

    Invalid UTF-8 becomes U+FFFD, as the in-memory decoders did before.
    """
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    # Both generators run lazily, so the final decode follows every chunk.
    texts = itertools.chain(
        (decoder.decode(chunk) for chunk in chunks),
        (decoder.decode(b"", final=True) for _ in (None,)),
    )
    escaped = (json.dumps(text)[1:-1].encode("ascii") for text in texts if text)
    return itertools.chain((b'"',), escaped, (b'"',))


class JsonArrayWriter:
    """Write a JSON array of records into a spool, one record at a time."""

    def __init__(self) -> None:
        self._spool = new_spool()
        self._count = 0
        self._spool.write(b"[")

    def add(
        self,
        fields: Mapping[str, object],
        streams: Mapping[str, IO[bytes]] | None = None,
    ) -> None:
        """Append one record; each ``streams`` value becomes a string field."""
        write = self._spool.write
        write(b"," if self._count else b"")
        write(b"{")
        members = 0
        for key, value in fields.items():
            write((b"," if members else b"") + json.dumps(key).encode())
            write(b":" + json.dumps(value, separators=(",", ":")).encode())
            members += 1
        for key, spool in (streams or {}).items():
            write((b"," if members else b"") + json.dumps(key).encode() + b":")
            for chunk in json_string_chunks(iter_spool(spool)):
                write(chunk)
            members += 1
        write(b"}")
        self._count += 1

    @property
    def count(self) -> int:
        """Return the number of records written."""
        return self._count

    def finish(self) -> StreamedContent:
        """Close the array and return its content."""
        self._spool.write(b"]")
        self._spool.flush()
        return StreamedContent(self._spool, event_count=self._count)
