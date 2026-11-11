"""The released TechVault pack binds environment from its own adapter (#1700)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
import yaml

from aptl.core.deployment._compose_node_generation import (
    base_compose_file,
)
from aptl.core.deployment._compose_runtime_config import (
    compose_readback,
)
from aptl.core.deployment.docker_compose import DockerComposeBackend
from aptl.core.deployment.runtime_materialization import (
    SHARED_DOCKER_PROFILE,
    effective_runtime_contract_issues,
)
from tests.test_compose_environment_bindings import (
    _ADAPTER,
    _CANARY,
    _compose_env,
    _delivered,
    _interpolates_nothing,
)

_TECHVAULT_WAZUH = ("INDEXER_USERNAME", "INDEXER_PASSWORD", "API_USERNAME")


_TECHVAULT_SOURCED = {
    "wazuh-manager": {*_TECHVAULT_WAZUH, "API_PASSWORD"},
    "wazuh-dashboard": {
        *_TECHVAULT_WAZUH,
        "API_PASSWORD",
        "DASHBOARD_USERNAME",
        "DASHBOARD_PASSWORD",
    },
    "misp": {"ADMIN_KEY"},
    "shuffle-backend": {"SHUFFLE_DEFAULT_USERNAME", "SHUFFLE_DEFAULT_PASSWORD"},
}


@pytest.fixture(scope="module")
def techvault(tmp_path_factory):
    """The released TechVault realization and its own startup adapter plan."""

    from aptl.backends.scenario_startup import ScenarioStartupSelection
    from aptl.core.scenario_bundle import env_pack_bundle
    from aptl_techvault.startup import TechVaultStartupProvider
    from tests.techvault.pack import _pack_root, realize_techvault_pack

    root = tmp_path_factory.mktemp("techvault-bindings")
    realization = realize_techvault_pack(root / "plan")
    bundle = env_pack_bundle(
        root / "bundle", identity="techvault", source_pack=_pack_root()
    )
    selection = ScenarioStartupSelection(
        identity=realization.pack_identity,
        provider=TechVaultStartupProvider,
        plan=TechVaultStartupProvider.resolve(bundle),
    )
    return realization.deployment_spec(
        sorted(realization.profiles), startup_selection=selection
    )


def test_the_released_techvault_pack_binds_from_its_own_adapter(
    techvault, tmp_path, monkeypatch
):
    """Every value-less Wazuh, MISP and Shuffle variable has an adapter source."""

    names = sorted(set().union(*_TECHVAULT_SOURCED.values()))
    (tmp_path / ".env").write_text(
        "".join(f"{name}={_ADAPTER}\n" for name in names), encoding="utf-8"
    )
    for name in names:
        monkeypatch.setenv(name, _CANARY)
    backend = DockerComposeBackend(tmp_path)

    assert backend._environment_binding_preflight(techvault) is None

    delivered = _delivered(backend, techvault, tmp_path)
    assert {
        service: {line.split("=", 1)[0] for line in text.splitlines()}
        for service, text in delivered.items()
    } == _TECHVAULT_SOURCED
    assert _CANARY not in "".join(delivered.values())
    assert _CANARY not in _compose_env(backend, monkeypatch).values()


def test_the_released_techvault_model_is_escaped_and_passes_the_model_check(
    techvault, tmp_path
):
    """The catalog's misp-redis `"$@"` pass-through is written as `"$$@"`."""

    text = base_compose_file(techvault, tmp_path).read_text(encoding="utf-8")
    model = yaml.safe_load(text)

    entrypoint = model["services"]["misp-redis"]["entrypoint"]
    assert entrypoint[2].endswith('exec docker-entrypoint.sh "$$@"')
    assert _interpolates_nothing(text)
    readback = compose_readback(model)
    issues = effective_runtime_contract_issues(
        readback, techvault, profile=SHARED_DOCKER_PROFILE
    )
    assert issues == ()


def test_the_released_techvault_readback_records_no_adapter_value_or_digest(
    techvault,
):
    """After start, evidence names no adapter value and commits to none.

    The readback sees each service with its adapter values in place. The six
    Wazuh and Shuffle ``secret_fixture`` names are left out of the disclosed
    environment,
    MISP's ``operator_secret`` ``ADMIN_KEY`` is disclosed by presence, and every
    commitment left is the one RAES derives from the scenario's own value.
    """

    from raes_processor.semantics.realization import project_realization_concern

    from aptl.backends._raes_runtime_environment_observation import (
        observe_environment,
    )

    disclosed: dict[str, list[dict[str, object]]] = {}
    for node in techvault.nodes:
        if node.name in _TECHVAULT_SOURCED:
            declared = node.runtime.environment
            info = {
                "Config": {"Env": [f"{v.name}={v.value or _ADAPTER}" for v in declared]}
            }
            disclosed[node.name] = observe_environment(info, node.runtime)
            authored = [v.model_dump(mode="json", by_alias=True) for v in declared]
            planned = project_realization_concern("runtime-environment", authored)
            assert [r for r in disclosed[node.name] if "value_commitment" in r] == [
                r for r in planned if "value_commitment" in r
            ]

    assert {
        service: {r["name"] for r in records} & _TECHVAULT_SOURCED[service]
        for service, records in disclosed.items()
    } == {
        "wazuh-manager": set(),
        "wazuh-dashboard": set(),
        "misp": {"ADMIN_KEY"},
        "shuffle-backend": set(),
    }
    admin_key = next(r for r in disclosed["misp"] if r["name"] == "ADMIN_KEY")
    assert admin_key["value_present"] is True
    assert "value_commitment" not in admin_key
    assert _ADAPTER not in json.dumps(disclosed)


def test_the_released_techvault_pack_without_its_env_stops_before_mutation(
    techvault, tmp_path
):
    backend = DockerComposeBackend(tmp_path)
    backend._run = MagicMock()

    result = backend._environment_binding_preflight(techvault)

    assert result is not None
    assert "has no value" in result.error
    backend._run.assert_not_called()
