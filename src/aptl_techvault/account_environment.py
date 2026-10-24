"""Which TechVault account credential each backend variable carries.

The pack declares every SOC console login as an SDL account with an authored
``secret_fixture`` binding. This module maps a backend variable name to the
account and credential it carries; core reads the username or value from the
admitted SDL. No value is written here, so a pack change to a credential
reaches the lab without an adapter edit.
"""

from __future__ import annotations

from aptl.backends.scenario_startup import AccountCredentialFixture

#: ``(account, credential id, ((variable, part), ...))`` for each declared login.
_ACCOUNT_VARIABLES = (
    (
        "wazuh-indexer-admin",
        "wazuh-indexer-admin-primary",
        (("INDEXER_USERNAME", "username"), ("INDEXER_PASSWORD", "secret")),
    ),
    (
        "wazuh-indexer-kibanaserver",
        "wazuh-indexer-kibanaserver-primary",
        (("DASHBOARD_USERNAME", "username"), ("DASHBOARD_PASSWORD", "secret")),
    ),
    (
        "wazuh-manager-api",
        "wazuh-manager-api-primary",
        (("API_USERNAME", "username"), ("API_PASSWORD", "secret")),
    ),
    (
        "shuffle-administrator",
        "shuffle-administrator-primary",
        (
            ("SHUFFLE_DEFAULT_USERNAME", "username"),
            ("SHUFFLE_DEFAULT_PASSWORD", "secret"),
        ),
    ),
    (
        "thehive-administrator",
        "thehive-administrator-primary",
        (("THEHIVE_ADMIN_USER", "username"), ("THEHIVE_ADMIN_PASS", "secret")),
    ),
    (
        "cortex-administrator",
        "cortex-administrator-primary",
        (
            ("CORTEX_SUPERADMIN_USER", "username"),
            ("CORTEX_SUPERADMIN_PASSWORD", "secret"),
        ),
    ),
)

#: Variables the seed scripts read to act as the declared console administrators.
SEED_ADMINISTRATOR_KEYS = (
    "THEHIVE_ADMIN_USER",
    "THEHIVE_ADMIN_PASS",
    "CORTEX_SUPERADMIN_USER",
    "CORTEX_SUPERADMIN_PASSWORD",
)


def techvault_account_environment() -> tuple[AccountCredentialFixture, ...]:
    """Return each backend variable as a reference to its declared credential."""

    return tuple(
        AccountCredentialFixture(name, account, credential_id, part)
        for account, credential_id, variables in _ACCOUNT_VARIABLES
        for name, part in variables
    )


__all__ = ("SEED_ADMINISTRATOR_KEYS", "techvault_account_environment")
