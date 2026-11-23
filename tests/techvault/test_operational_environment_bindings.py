"""TechVault startup providers grant only their own pack identity (#1700)."""

import pytest


@pytest.mark.parametrize("study", [False, True])
def test_inherited_startup_plan_uses_its_providers_own_pack_identity(study):
    from aptl_techvault.startup import TechVaultStartupProvider
    from aptl_techvault.study import StudyStartup

    provider = StudyStartup if study else TechVaultStartupProvider
    plan = provider.resolve(None)
    assert plan.environment_grants
    assert {grant.pack for grant in plan.environment_grants} == {
        provider.supported_pack_id
    }
