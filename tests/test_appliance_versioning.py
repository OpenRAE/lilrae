"""Bounded wheel-name parsing for the appliance application wheel."""

from __future__ import annotations

import pytest

from aptl.appliance.versioning import aptl_wheel_version, is_appliance_version


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("lilrae-8.0.0-py3-none-any.whl", "8.0.0"),
        ("wheelhouse/lilrae-8.1.2rc1-py3-none-any.whl", "8.1.2rc1"),
        ("lilrae-8.0.0_dev1-py3-none-any.whl", "8.0.0-dev1"),
        # The legacy distribution's wheels are not the application wheel.
        ("aptl_labs-7.0.0-py3-none-any.whl", None),
        ("lilrae-8.0.0.whl", None),
        ("lilrae-8.0-py3-none-any.whl", None),
        ("lilrae-8.0.0-py3-none-any.tar.gz", None),
        ("lilrae-8.0.0;x-py3-none-any.whl", None),
    ],
)
def test_wheel_version_accepts_only_the_lilrae_application_wheel(name, expected):
    assert aptl_wheel_version(name) == expected


def test_wheel_version_prefix_stays_a_parameter():
    assert aptl_wheel_version("other-1.2.3-py3-none-any.whl", prefix="other-") == "1.2.3"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("8.0.0", True), ("10.20.30+local.1", True), ("8.0", False), ("8.x.0", False)],
)
def test_appliance_version_shape(value, expected):
    assert is_appliance_version(value) is expected
