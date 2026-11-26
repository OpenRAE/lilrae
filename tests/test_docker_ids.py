"""Tests for Docker's exact container-ID and image-ID forms."""

import pytest

from aptl.core.docker_ids import is_container_id, is_image_id

FULL_ID = "c0ffee" + "1" * 58


@pytest.mark.parametrize("value", [FULL_ID, "0" * 64])
def test_accepts_a_full_container_id(value):
    assert is_container_id(value)


@pytest.mark.parametrize(
    "value",
    [
        FULL_ID[:12],
        FULL_ID + "0",
        FULL_ID.upper(),
        f"sha256:{FULL_ID}",
        f"{FULL_ID}\n",
        "",
        None,
        64,
    ],
    ids=[
        "truncated",
        "too-long",
        "uppercase",
        "image-id-form",
        "trailing-newline",
        "empty",
        "none",
        "not-a-string",
    ],
)
def test_rejects_anything_else_as_a_container_id(value):
    assert not is_container_id(value)


def test_accepts_an_image_id():
    assert is_image_id(f"sha256:{FULL_ID}")


@pytest.mark.parametrize(
    "value",
    [
        FULL_ID,
        f"sha256:{FULL_ID[:12]}",
        f"sha256:{FULL_ID.upper()}",
        f"sha512:{FULL_ID}",
        f"sha256:{FULL_ID}\n",
        "aptl/victim:latest",
        None,
    ],
    ids=[
        "container-id-form",
        "truncated",
        "uppercase",
        "other-algorithm",
        "trailing-newline",
        "tag",
        "none",
    ],
)
def test_rejects_anything_else_as_an_image_id(value):
    assert not is_image_id(value)
