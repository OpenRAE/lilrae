"""Every released TechVault account provider resolves its ingress (#1700)."""

from __future__ import annotations

from aptl.core.deployment import _account_provider as provider
from aptl.core.deployment import _compose_application_accounts as accounts


def test_every_released_techvault_account_provider_resolves_its_ingress(released_techvault_realization):
    """Each SOC product the released pack declares is reachable (#1273)."""

    realization = released_techvault_realization
    spec = realization.deployment_spec(sorted(realization.profiles))
    resolved = {
        node.backend_account_provider: accounts.product_ingress(
            node.backend_account_provider, node, spec.nodes
        )
        for node in spec.nodes
        if node.backend_account_provider in provider.APPLICATION_ACCOUNT_PROVIDERS
    }

    assert set(resolved) == set(provider.APPLICATION_ACCOUNT_PROVIDERS)
    assert {kind: item.base_url for kind, item in resolved.items()} == {
        provider.OPENSEARCH_SECURITY: "https://localhost:9200",
        provider.WAZUH_API: "https://localhost:55000",
        provider.MISP: "https://localhost:443",
        provider.SHUFFLE: "https://localhost:443",
    }
    assert resolved[provider.SHUFFLE].container == "aptl-shuffle-frontend"
