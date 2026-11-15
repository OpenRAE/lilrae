"""Tests for streamed capture validation and element-wise redaction."""

from __future__ import annotations

import json

import pytest

from aptl.core.evidence._stream_prepare import prepare_stream
from aptl.utils.redaction import redact


def _split(data: bytes, *points: int) -> list[bytes]:
    """Cut ``data`` at the given offsets."""
    edges = [0, *points, len(data)]
    return [data[start:end] for start, end in zip(edges, edges[1:], strict=False)]


def _run(chunks, media_type, *, redacted):
    return b"".join(prepare_stream(chunks, media_type, redacted=redacted))


_JSON = '{"note":"café ☕","count":12,"values":[1,2.5,true,null]}'.encode()
# Offsets inside "é" (a two-byte character) and inside the "count" token.
_AWKWARD = (_JSON.index("é".encode()) + 1, _JSON.index(b"count") + 2)


@pytest.mark.parametrize(
    "media_type", ["application/json", "application/x-ndjson", "text/plain"]
)
def test_unredacted_content_passes_through_byte_for_byte(media_type):
    data = _JSON + b"\n" if media_type != "application/json" else _JSON

    assert _run(_split(data, *_AWKWARD), media_type, redacted=False) == data


def test_unredacted_jsonl_keeps_its_original_bytes():
    data = b'{"a":1}\n\n{"b":  [1, 2]}\n{"c":3}'

    assert _run(_split(data, 3, 12), "application/x-ndjson", redacted=False) == data


@pytest.mark.parametrize(
    ("media_type", "data"),
    [
        ("application/json", b'{"a":'),
        ("application/json", b'{"a":1} trailing'),
        ("application/json", b"not json"),
        ("application/x-ndjson", b'{"a":1}\n{broken\n'),
    ],
)
def test_invalid_json_raises_value_error(media_type, data):
    with pytest.raises(ValueError):
        _run(_split(data, 2), media_type, redacted=False)


@pytest.mark.parametrize("redacted", [False, True])
def test_empty_json_raises_value_error(redacted):
    with pytest.raises(ValueError):
        _run([b"", b"  \n"], "application/json", redacted=redacted)


def test_invalid_utf8_text_raises():
    with pytest.raises(UnicodeDecodeError):
        _run([b"ok \xff"], "text/plain", redacted=False)


_OBJECT = {
    "password": "hunter2",
    "nested": {"api_key": "k", "keep": "value"},
    "args": ["hydra", "-p", "secret-value", "--password", "pw", "host"],
    "log": "Authorization: Bearer abc.def.ghi",
    "count": 3,
    "ratio": 0.25,
}
_ARRAY = [
    {"token": "t", "ok": 1},
    "--password",
    "pw",
    "-p",
    "8080",
    ["mysql", "-psecret"],
]


@pytest.mark.parametrize("document", [_OBJECT, _ARRAY, "Bearer abc.def", 7, None])
def test_redacted_json_equals_the_canonical_redaction(document):
    data = json.dumps(document).encode()

    output = _run(_split(data, 1, len(data) // 2), "application/json", redacted=True)

    assert json.loads(output) == redact(document)


def test_redacted_argv_document_matches_the_canonical_list_rules():
    document = ["hydra", "-l", "admin", "-p", "hunter2", "ssh://host"]

    output = _run([json.dumps(document).encode()], "application/json", redacted=True)

    assert json.loads(output) == redact(document)
    assert "hunter2" not in output.decode()


def test_redacted_json_lines_are_redacted_one_record_at_a_time():
    records = [_OBJECT, {"plain": "x"}, _ARRAY]
    data = b"".join(json.dumps(item).encode() + b"\n" for item in records)

    output = _run(_split(data, 5, 40, 90), "application/x-ndjson", redacted=True)

    lines = output.decode().splitlines()
    assert [json.loads(line) for line in lines] == [redact(item) for item in records]


_PEM = (
    "start\n"
    "-----BEGIN PRIVATE KEY-----\n"
    "MIIBVwIBADANBgkqhkiG9w0BAQEFAASCAUEwggE9AgEAAkEA\n"
    "-----END PRIVATE KEY-----\n"
    "password=hunter2\n"
    "end without newline"
)


def test_redacted_text_keeps_a_pem_block_together_and_keeps_layout():
    data = _PEM.encode()

    output = _run(_split(data, 10, 40, 70), "text/plain", redacted=True).decode()

    # The PEM body is removed only when its BEGIN and END lines are redacted
    # as one group.
    assert "MIIBVwIBADANBgkq" not in output
    assert "hunter2" not in output
    assert output.startswith("start\n")
    assert output.endswith("end without newline")


def test_redaction_of_unsupported_media_raises():
    with pytest.raises(ValueError):
        list(prepare_stream([b"\x00\x01"], "application/zip", redacted=True))


def test_unsupported_media_without_redaction_passes_through():
    chunks = [b"\x00\x01", b"\x02"]

    assert _run(chunks, "application/zip", redacted=False) == b"\x00\x01\x02"
