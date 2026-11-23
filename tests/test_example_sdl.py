"""The checked-in example SDLs parse under the pinned RAES authoring contract."""

from pathlib import Path

import pytest

EXAMPLES = sorted((Path(__file__).resolve().parents[1] / "examples").glob("*.sdl.yaml"))


def test_examples_are_present():
    assert EXAMPLES


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.name)
def test_example_parses_without_legacy_migration(path):
    """The default parser rejects legacy syntax, so each example is current SDL."""
    from raes import parse_sdl_file

    assert parse_sdl_file(path).nodes
