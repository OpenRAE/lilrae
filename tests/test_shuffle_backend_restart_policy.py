"""Issue #1423: Docker restarts the Shuffle backend after its init panic.

Upstream shuffle-shared dereferences a nil response when an OpenSearch
index-create request times out, and the backend exits with status 2. The
released TechVault pack leaves the restart policy open, so the
``shuffle-backend`` profile selects ``on_failure``. These tests drive the real
selection, Compose lowering and daemon readback for that pack.
"""

from __future__ import annotations

import pytest
from raes_processor.semantics.realization import CONCERN_PAYLOAD_PATH

from aptl.backends.raes_observation import observe_realization
from aptl.core.deployment._compose_node_generation import render_realization_compose
from tests.techvault_pack import plan_techvault_pack
from tests.test_raes_runtime_observation import _Backend, _inspect

_BACKEND = "shuffle-backend"
_RESTART_POLICY = "runtime-restart-policy"


class _DaemonBackend(_Backend):
    """Daemon readback stub; image-digest attestation is not under test."""

    def container_image_digest(self, _name):
        return None


@pytest.fixture(scope="module")
def released(tmp_path_factory):
    """Return the plan and realization of the unmodified released pack."""

    return plan_techvault_pack(tmp_path_factory.mktemp("techvault"))


def _backend_node(realization):
    return next(node for node in realization.nodes if node.name == _BACKEND)


def _realized_restart_policies(realization) -> dict[str, str]:
    policies = {}
    for node in realization.nodes:
        policy = getattr(node.runtime, "operational_policy", None)
        if policy is not None and policy.restart is not None:
            policies[node.name] = policy.restart.value
    return policies


def _compose_restart_policies(realization) -> dict[str, str]:
    spec = realization.deployment_spec(sorted(realization.profiles))
    services = render_realization_compose(spec)["services"]
    return {
        name: service["restart"]
        for name, service in services.items()
        if "restart" in service
    }


def _declaring_backend_restart(policy: str):
    def edit(document: dict) -> None:
        runtime = document["nodes"][_BACKEND]["runtime"]
        runtime["operational_policy"] = {"restart": policy}

    return edit


def test_released_pack_restarts_only_the_shuffle_backend_on_failure(released):
    _plan, realization = released

    assert _RESTART_POLICY in _backend_node(realization).backend_selected_concerns
    assert _realized_restart_policies(realization) == {_BACKEND: "on_failure"}
    assert _compose_restart_policies(realization) == {_BACKEND: "on-failure"}


@pytest.mark.parametrize(
    ("declared", "realized", "compose", "selected"),
    [
        # An authored policy wins over the profile.
        ("no", "no", "no", False),
        # An explicit "unknown" leaves the concern open, like an absent one.
        ("unknown", "on_failure", "on-failure", True),
    ],
)
def test_sdl_declared_restart_policy_wins_over_the_profile(
    tmp_path, declared, realized, compose, selected
):
    _plan, realization = plan_techvault_pack(
        tmp_path, edit_sdl=_declaring_backend_restart(declared)
    )

    selected_concerns = _backend_node(realization).backend_selected_concerns
    assert (_RESTART_POLICY in selected_concerns) is selected
    assert _realized_restart_policies(realization) == {_BACKEND: realized}
    assert _compose_restart_policies(realization) == {_BACKEND: compose}


@pytest.mark.parametrize(
    ("daemon_policy", "disclosed"),
    [("on-failure", "on_failure"), ("no", "no")],
)
def test_daemon_readback_discloses_the_backend_restart_policy(
    released, tmp_path, daemon_policy, disclosed
):
    plan, realization = released
    node = _backend_node(realization)
    backend = _DaemonBackend({node.container_name: _inspect(restart=daemon_policy)})

    observations = observe_realization(backend, realization, plan, tmp_path)

    concerns = observations[node.address].concerns
    assert concerns[CONCERN_PAYLOAD_PATH[_RESTART_POLICY]] == disclosed
