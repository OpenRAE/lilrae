"""TechVault's Redis authorization observation requires a bounded live ACL (#1700)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.test_raes_runtime_observation import (
    _APP_AUTH_PATH,
    _CONTAINER,
    _Backend,
    _inspect,
    _redis_acl_runtime,
)


def test_techvault_redis_authorization_requires_bounded_live_acl():
    from aptl_techvault.startup import TechVaultStartupProvider

    backend = _Backend(
        {_CONTAINER: _inspect()},
        exec_results={
            _CONTAINER: {
                "sh": (
                    0,
                    "config=exact\nauth=PONG\nrw=verified\nadmin=denied\n",
                )
            }
        },
    )

    observed = TechVaultStartupProvider.observe_runtime(
        backend,
        SimpleNamespace(
            name="misp-redis",
            container_name=_CONTAINER,
            runtime=_redis_acl_runtime(),
        ),
    )

    assert _APP_AUTH_PATH in observed


def test_techvault_redis_authorization_rejects_admin_access():
    from aptl_techvault.startup import TechVaultStartupProvider

    backend = _Backend(
        {_CONTAINER: _inspect()},
        exec_results={
            _CONTAINER: {
                "sh": (
                    0,
                    "config=exact\nauth=PONG\nrw=verified\nadmin=allowed\n",
                )
            }
        },
    )

    observed = TechVaultStartupProvider.observe_runtime(
        backend,
        SimpleNamespace(
            name="misp-redis",
            container_name=_CONTAINER,
            runtime=_redis_acl_runtime(),
        ),
    )

    assert _APP_AUTH_PATH not in observed


@pytest.mark.parametrize(
    "readback",
    [
        "config=exact\nauth=PONG\nrw=verified\nadmin=allowed\n",
        "config=exact\nauth=PONG\nrw=verified\nadmin=denied\nextra=value\n",
        "config=exact\nauth=PONG\nrw=verified\nadmin=denied\nadmin=denied\n",
        "config=exact\nauth=PONG\nrw=verified\nadmin\n",
    ],
)
def test_techvault_redis_authorization_rejects_malformed_readback(readback):
    from aptl_techvault.redis_acl_observation import _readback_verified

    assert not _readback_verified(SimpleNamespace(stdout=readback))
