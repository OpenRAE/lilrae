"""Direct env-pack acquisition refuses a path-shaped identity (#875, #1700).

The released-pack compatibility cases live with the adapter tests.
"""

from __future__ import annotations

import pytest

from aptl.core.scenario_bundle import (
    EnvPackError,
    env_pack_bundle,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("identity", ["../escape", "/tmp/escape", "a/b", ".", ".."])
def test_direct_acquisition_rejects_path_like_identity(tmp_path, identity):
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(EnvPackError, match="identity"):
        env_pack_bundle(tmp_path / "staged", identity, source_pack=source)
