"""The released TechVault plan carries credential results (#1700)."""

from __future__ import annotations

import importlib.resources as ir
from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from raes.runtime_configuration import RuntimeCapabilityPolicy
from raes_contracts.planning import (
    ProvisioningPlan,
)
from raes_contracts.run_scope import PlanScope
from raes_runtime.backend_account_credentials import (
    plan_has_account_credentials,
)

from aptl.backends.raes_observation import ObservedResource
from tests.test_raes_credential_result_contract import (
    _ACCOUNT,
    _CAPABILITIES,
    _NODE,
    _NODE_TYPE,
    _closure_refusal,
    _differing_observations,
    _readback,
    _readback_plan,
)


@pytest.fixture(scope="module")
def techvault_plan(tmp_path_factory) -> ProvisioningPlan:
    """Plan the installed TechVault pack, whose SOC logins carry credentials."""

    from aptl.backends.raes import (
        RuntimeManager,
        create_aptl_runtime_target,
        parse_sdl_file,
    )
    from aptl.core.config import AptlConfig
    from aptl.core.scenario_bundle import env_pack_bundle
    from tests.techvault.pack import _TECHVAULT_FLAG_PARAMETERS, PROJECT_ROOT

    pack = ir.files("raes_env_packs") / "resources" / "packs" / "techvault"
    bundle = env_pack_bundle(
        tmp_path_factory.mktemp("credential-result"),
        identity="techvault",
        source_pack=pack,
    )
    config = AptlConfig(
        lab={"name": "tv"},
        containers={
            "profiles": ["wazuh", "soc", "enterprise", "victim", "kali", "fileshare", "dns"]
        },
    )
    target = create_aptl_runtime_target(
        project_dir=PROJECT_ROOT, config=config, backend=MagicMock(), bundle=bundle
    )
    plan = RuntimeManager(target).plan(
        parse_sdl_file(bundle.sdl_path),
        parameters=_TECHVAULT_FLAG_PARAMETERS,
        run_scope=PlanScope(run_id="credential-result"),
    ).provisioning
    assert plan_has_account_credentials(plan)
    return plan


def test_differing_observations_are_admitted_under_rae_1640(techvault_plan):
    """The supported RAES release admits observed concerns that differ (rae#1640)."""

    differing = _differing_observations(techvault_plan)

    assert _closure_refusal(techvault_plan, differing) is None


def test_retained_materialization_null_does_not_delay_or_fail_readback(
    monkeypatch,
    techvault_plan,
):
    assert techvault_plan.materialization_source is not None
    plan = replace(
        _readback_plan(kind="domain-topology"),
        materialization_source=techvault_plan.materialization_source,
    )
    observed = ObservedResource(realized=True, concerns={_NODE_TYPE: "vm"})
    observations = {_NODE: observed, _ACCOUNT: ObservedResource(realized=True)}

    assert _closure_refusal(plan, observations) is None
    result, sleeps = _readback(monkeypatch, plan, [observed])

    assert result.success
    assert sleeps == []


@pytest.mark.parametrize("credentials", [True, False])
def test_invalid_materialization_null_waits_only_for_credential_plans(
    monkeypatch,
    techvault_plan,
    credentials,
):
    plan = replace(
        _readback_plan(kind="linux-capabilities", credentials=credentials),
        materialization_source=techvault_plan.materialization_source,
    )
    first = ObservedResource(realized=True, concerns={_NODE_TYPE: "vm"})
    late = ObservedResource(
        realized=True,
        concerns={
            _NODE_TYPE: "vm",
            _CAPABILITIES: RuntimeCapabilityPolicy().model_dump(mode="json"),
        },
    )
    assert _closure_refusal(plan, {_NODE: late, _ACCOUNT: ObservedResource(True)}) is None

    result, sleeps = _readback(monkeypatch, plan, [first, late])

    assert result.success
    assert sleeps == ([2.0] if credentials else [])
