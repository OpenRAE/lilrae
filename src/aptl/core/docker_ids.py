"""Docker's exact forms of a full container ID and of an image ID.

A full container ID is 64 lowercase hexadecimal characters. An image ID is
``sha256:`` and 64 lowercase hexadecimal characters. A truncated, uppercase,
or prefixed value is not in either form.
"""

import re
from typing import TypeGuard

__all__ = ["is_container_id", "is_image_id"]

_CONTAINER_ID = re.compile(r"[0-9a-f]{64}", re.ASCII)
_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


def is_container_id(value: object) -> TypeGuard[str]:
    """Return whether ``value`` is a full Docker container ID."""
    return isinstance(value, str) and _CONTAINER_ID.fullmatch(value) is not None


def is_image_id(value: object) -> TypeGuard[str]:
    """Return whether ``value`` is a Docker image ID (``sha256:<64 hex>``)."""
    return isinstance(value, str) and _IMAGE_ID.fullmatch(value) is not None
