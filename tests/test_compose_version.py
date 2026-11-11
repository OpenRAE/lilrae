"""Docker Compose capability parsing on supported guest distributions."""

import pytest

from aptl.core.deployment._compose_stateful_graph import compose_version


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("2.40.3+ds1-0ubuntu1", (2, 40, 3)),
        ("Docker Compose version v2.24.4", (2, 24, 4)),
        ("v2.24.3-rc1+build", (2, 24, 3)),
        ("not a version", None),
    ],
)
def test_compose_version_accepts_distribution_build_suffix(
    output: str, expected: tuple[int, int, int] | None
) -> None:
    assert compose_version(output) == expected


def test_only_emitted_merge_features_require_the_override_floor(tmp_path):
    from aptl.core.deployment._lilrae_compose_capabilities import compose_feature_minimum
    path = tmp_path / 'compose.yml'
    path.write_text('services:\n  example:\n    image: example:test\n')
    assert compose_feature_minimum((path,)) == (2, 0, 0)
    path.write_text('services:\n  example:\n    ports: !override []\n')
    assert compose_feature_minimum((path,)) == (2, 24, 4)
    path.write_text('services:\n  example:\n    build: !reset null\n')
    assert compose_feature_minimum((path,)) == (2, 24, 4)
