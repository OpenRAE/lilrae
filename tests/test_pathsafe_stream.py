"""Tests for streamed, content-addressed and named create-once writes."""

from __future__ import annotations

import hashlib
import os

import pytest

from aptl.utils.pathsafe import PathContainmentError
from aptl.utils.pathsafe_stream import (
    FreeSpaceReserveError,
    create_content_addressed_nofollow,
    create_exclusive_stream_nofollow,
    require_free_space,
)

_CHUNKS = [bytes([index]) * 4099 for index in range(64)]
_DATA = b"".join(_CHUNKS)
_DIGEST = hashlib.sha256(_DATA).hexdigest()


def _names(directory):
    return sorted(os.listdir(directory))


def test_many_chunks_are_stored_under_their_digest(tmp_path):
    digest, size = create_content_addressed_nofollow(
        tmp_path, "run/blobs", iter(_CHUNKS), reserve_fraction=0.0
    )

    assert (digest, size) == (_DIGEST, len(_DATA))
    assert (tmp_path / "run/blobs" / _DIGEST).read_bytes() == _DATA
    assert _names(tmp_path / "run/blobs") == [_DIGEST]


def test_identical_content_is_accepted_again(tmp_path):
    for _ in range(2):
        result = create_content_addressed_nofollow(
            tmp_path, "blobs", iter(_CHUNKS), reserve_fraction=0.0
        )

    assert result == (_DIGEST, len(_DATA))
    assert _names(tmp_path / "blobs") == [_DIGEST]


def test_different_bytes_at_the_digest_name_are_refused(tmp_path):
    (tmp_path / "blobs").mkdir()
    (tmp_path / "blobs" / _DIGEST).write_bytes(b"other content")

    chunks = iter(_CHUNKS)
    with pytest.raises(FileExistsError):
        create_content_addressed_nofollow(
            tmp_path, "blobs", chunks, reserve_fraction=0.0
        )
    assert _names(tmp_path / "blobs") == [_DIGEST]


def test_a_symlinked_directory_component_is_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "blobs").symlink_to(outside, target_is_directory=True)

    base, chunks = tmp_path / "base", iter(_CHUNKS)
    with pytest.raises(PathContainmentError):
        create_content_addressed_nofollow(base, "blobs", chunks, reserve_fraction=0.0)
    assert _names(outside) == []


def test_an_unreachable_reserve_fails_and_leaves_no_file(tmp_path):
    chunks = iter(_CHUNKS)
    with pytest.raises(FreeSpaceReserveError) as caught:
        create_content_addressed_nofollow(
            tmp_path, "blobs", chunks, reserve_fraction=0.999999
        )

    assert caught.value.errno is not None
    assert _names(tmp_path / "blobs") == []


def test_require_free_space_accepts_a_zero_reserve(tmp_path):
    fd = os.open(tmp_path, os.O_RDONLY)
    try:
        require_free_space(fd, 0.0)
        with pytest.raises(FreeSpaceReserveError):
            require_free_space(fd, 1.0)
    finally:
        os.close(fd)


def test_named_stream_accepts_identical_and_refuses_different_content(tmp_path):
    first = create_exclusive_stream_nofollow(
        tmp_path, "run/a/file.bin", iter(_CHUNKS), reserve_fraction=0.0
    )
    again = create_exclusive_stream_nofollow(
        tmp_path, "run/a/file.bin", iter(_CHUNKS), reserve_fraction=0.0
    )

    assert first == again == (_DIGEST, len(_DATA))
    assert (tmp_path / "run/a/file.bin").read_bytes() == _DATA
    with pytest.raises(FileExistsError):
        create_exclusive_stream_nofollow(
            tmp_path, "run/a/file.bin", [b"different"], reserve_fraction=0.0
        )
    assert (tmp_path / "run/a/file.bin").read_bytes() == _DATA
    assert _names(tmp_path / "run/a") == ["file.bin"]


def test_a_failing_source_leaves_no_temporary_file(tmp_path):
    def chunks():
        yield b"partial"
        raise RuntimeError("source failed")

    source = chunks()
    with pytest.raises(RuntimeError):
        create_exclusive_stream_nofollow(
            tmp_path, "run/file.bin", source, reserve_fraction=0.0
        )
    assert _names(tmp_path / "run") == []
