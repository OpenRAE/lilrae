"""Tests for evidence spool files and streamed JSON records."""

from __future__ import annotations

import json
import os

from aptl.core.evidence.spool import (
    JsonArrayWriter,
    StreamedContent,
    json_string_chunks,
    new_spool,
    spool_directory,
)


def test_spools_are_created_in_the_selected_directory(tmp_path, monkeypatch):
    created = []
    real = os.open

    def recording_open(path, *args, **kwargs):
        created.append(str(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", recording_open)
    with spool_directory(tmp_path / "spool"):
        with new_spool() as spool:
            spool.write(b"data")

    assert (tmp_path / "spool").is_dir()
    assert any(path.startswith(str(tmp_path / "spool")) for path in created)


def test_json_string_chunks_join_a_split_multibyte_character():
    data = "a☕b".encode()
    split = data.index("☕".encode()) + 1

    encoded = b"".join(json_string_chunks([data[:split], data[split:]]))

    assert json.loads(encoded) == "a☕b"


def test_json_string_chunks_replace_invalid_utf8():
    raw = b"ok \xff end"

    encoded = b"".join(json_string_chunks([raw[:4], raw[4:]]))

    assert json.loads(encoded) == raw.decode("utf-8", errors="replace")


def test_writer_streams_large_fields_as_valid_json(tmp_path):
    output = ("line é\n" * 300_000).encode() + b"\xfe"
    with spool_directory(tmp_path), new_spool() as stream, new_spool() as empty:
        stream.write(output)
        writer = JsonArrayWriter()
        writer.add({"container": "web", "count": 2}, {"output": stream})
        writer.add({}, {"stderr": empty})
        writer.add({"status": "source-unavailable"})
        content = writer.finish()

    records = json.loads(b"".join(content))

    assert content.event_count == writer.count == 3
    assert records[0] == {
        "container": "web",
        "count": 2,
        "output": output.decode("utf-8", errors="replace"),
    }
    assert records[1] == {"stderr": ""}
    assert records[2] == {"status": "source-unavailable"}


def test_streamed_content_is_reiterable_and_falsy_when_empty(tmp_path):
    with spool_directory(tmp_path):
        empty = StreamedContent(new_spool(), event_count=0)
        full_spool = new_spool()
        full_spool.write(b"x" * (3 * 1024 * 1024 + 7))
        full = StreamedContent(full_spool, event_count=1)

    assert not empty
    assert list(empty) == []
    assert full
    first, second = b"".join(full), b"".join(full)
    assert first == second == b"x" * (3 * 1024 * 1024 + 7)


def test_an_empty_array_is_valid_json(tmp_path):
    with spool_directory(tmp_path):
        content = JsonArrayWriter().finish()

    assert json.loads(b"".join(content)) == []
    assert content.event_count == 0
