"""Validate and optionally redact one capture stream on its way to disk.

Content without a redaction policy passes through byte for byte while a push
parser checks that it is the declared media type. Content with a policy is
re-encoded one element at a time with the canonical redactor: one top-level
member or item of a JSON document, one JSON-lines record, or one line group of
text. Memory use therefore depends on the largest element, not on the size of
the capture.
"""

from __future__ import annotations

import codecs
import itertools
import json
from collections.abc import Callable, Iterable, Iterator

import ijson

from aptl.utils.redaction import iter_redact_list, redact, redact_mapping_item

JSON_MEDIA_TYPE = "application/json"
TEXT_MEDIA_TYPE = "text/plain"
JSON_LINES_MEDIA_TYPES = frozenset({"application/x-ndjson", "application/jsonl"})
REDACTABLE_MEDIA_TYPES = (
    frozenset({JSON_MEDIA_TYPE, TEXT_MEDIA_TYPE}) | JSON_LINES_MEDIA_TYPES
)
_PEM_BEGIN = b"-----BEGIN "
_PEM_END = b"-----END "


def _encode(value: object) -> bytes:
    """Encode one value as compact UTF-8 JSON."""
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def _drain(events: list[object]) -> list[object]:
    """Return and clear the values a push parser produced so far."""
    ready = list(events)
    del events[:]
    return ready


def _validated_json(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """Pass JSON bytes through unchanged after the parser accepts each chunk."""
    events = ijson.sendable_list()
    parser = ijson.basic_parse_coro(events)
    seen = False
    try:
        for chunk in chunks:
            # ijson reads an empty chunk as the end of the input.
            if chunk:
                parser.send(chunk)
                del events[:]
                seen = seen or bool(chunk.strip())
            yield chunk
        parser.close()
    except StopIteration:
        raise ValueError("capture JSON content has trailing data") from None
    if not seen:
        raise ValueError("capture JSON content is empty")


def _validated_text(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """Pass UTF-8 text through unchanged after the decoder accepts each chunk."""
    decoder = codecs.getincrementaldecoder("utf-8")()
    for chunk in chunks:
        decoder.decode(chunk)
        yield chunk
    decoder.decode(b"", final=True)


def _lines(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """Split a byte stream into lines, each with its line terminator if any."""
    pending = b""
    for chunk in chunks:
        pending += chunk
        *complete, pending = pending.split(b"\n")
        for line in complete:
            yield line + b"\n"
    if pending:
        yield pending


def _redacted_json_lines(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """Redact each JSON-lines record with the canonical redactor."""
    for line in _lines(chunks):
        if line.strip():
            yield _encode(redact(json.loads(line))) + b"\n"


def _validated_json_lines(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """Pass JSON-lines bytes through unchanged after each record parses."""
    pending = b""
    for chunk in chunks:
        pending += chunk
        *complete, pending = pending.split(b"\n")
        for line in complete:
            if line.strip():
                json.loads(line)
        yield chunk
    if pending.strip():
        json.loads(pending)


def _redact_text(data: bytes) -> bytes:
    """Redact one UTF-8 text group with the canonical redactor."""
    safe = redact(data.decode("utf-8"))
    if not isinstance(safe, str):
        raise TypeError("text redaction returned non-text")
    return safe.encode("utf-8")


def _redacted_text(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """Redact text one line at a time, keeping each PEM block in one group."""
    group: list[bytes] = []
    in_pem = False
    for line in _lines(chunks):
        group.append(line)
        in_pem = (in_pem or _PEM_BEGIN in line) and _PEM_END not in line
        if not in_pem:
            yield _redact_text(b"".join(group))
            group = []
    if group:
        yield _redact_text(b"".join(group))


def _parsed(
    chunks: Iterable[bytes], make_parser: Callable[[list[object]], object]
) -> Iterator[object]:
    """Feed ``chunks`` to an ijson push parser and yield each finished value."""
    events = ijson.sendable_list()
    parser = make_parser(events)
    try:
        for chunk in chunks:
            # ijson reads an empty chunk as the end of the input.
            if chunk:
                parser.send(chunk)  # type: ignore[attr-defined]
                yield from _drain(events)
        parser.close()  # type: ignore[attr-defined]
    except StopIteration:
        raise ValueError("capture JSON content has trailing data") from None
    yield from _drain(events)


def _redacted_object(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """Redact a top-level JSON object one member at a time."""
    members = _parsed(
        chunks, lambda events: ijson.kvitems_coro(events, "", use_float=True)
    )
    encoded = (
        (b"," if index else b"")
        + _encode(key)
        + b":"
        + _encode(redact_mapping_item(key, value))
        for index, (key, value) in enumerate(members)  # type: ignore[misc]
    )
    return itertools.chain((b"{",), encoded, (b"}",))


def _redacted_array(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """Redact a top-level JSON array one item at a time."""
    items = _parsed(
        chunks, lambda events: ijson.items_coro(events, "item", use_float=True)
    )
    encoded = (
        (b"," if index else b"") + _encode(item)
        for index, item in enumerate(iter_redact_list(items))
    )
    return itertools.chain((b"[",), encoded, (b"]",))


def _redacted_json(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """Redact one JSON document member by member or item by item."""
    source = iter(chunks)
    head = b""
    for chunk in source:
        head += chunk
        if head.strip():
            break
    first = head.lstrip()[:1]
    stream = itertools.chain([head], source)
    if first == b"{":
        yield from _redacted_object(stream)
    elif first == b"[":
        yield from _redacted_array(stream)
    elif first:
        values = _parsed(
            stream, lambda events: ijson.items_coro(events, "", use_float=True)
        )
        for value in values:
            yield _encode(redact(value))
    else:
        raise ValueError("capture JSON content is empty")


def _as_value_errors(stream: Iterator[bytes]) -> Iterator[bytes]:
    """Report ijson parse failures as ``ValueError`` like the stdlib parser."""
    try:
        yield from stream
    except ijson.JSONError as exc:
        raise ValueError(f"capture JSON content is invalid: {exc}") from exc


def prepare_stream(
    chunks: Iterable[bytes], media_type: str, *, redacted: bool
) -> Iterator[bytes]:
    """Return the bytes to persist for one capture stream.

    Raises ``ValueError`` (including ijson parse errors) or
    ``UnicodeDecodeError`` while the stream is consumed when the content is
    not the declared media type.
    """
    handlers = _HANDLERS.get(media_type)
    if handlers is None:
        if redacted:
            raise ValueError("capture media type has no trusted redaction adapter")
        return iter(chunks)
    return handlers[redacted](chunks)


_HANDLERS: dict[str, dict[bool, Callable[[Iterable[bytes]], Iterator[bytes]]]] = {
    JSON_MEDIA_TYPE: {
        True: lambda chunks: _as_value_errors(_redacted_json(chunks)),
        False: lambda chunks: _as_value_errors(_validated_json(chunks)),
    },
    TEXT_MEDIA_TYPE: {True: _redacted_text, False: _validated_text},
    **{
        media_type: {True: _redacted_json_lines, False: _validated_json_lines}
        for media_type in JSON_LINES_MEDIA_TYPES
    },
}
