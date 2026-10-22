"""Authored ``secret_fixture`` credentials reach the account provider (#1273).

An SDL account that declares its credential is declaring an in-world fact: the
password a participant or attacker meets. The account gate lowers exactly one
authored primary ``secret_fixture`` binding into the realization record, keeps
the value out of every evidence projection, and refuses any binding shape the
selected provider cannot realize instead of substituting another credential.
"""

from __future__ import annotations

import pytest
from raes_contracts.planning import PlannedResource, RuntimeDomain

from aptl.backends.raes_account_realization import resolve_account_placement
from aptl.core.deployment import _account_provider as provider

_VALUE = "In-World-Fixture-2026!"


def _binding(**overrides):
    binding = {
        "credential_id": "console-primary",
        "purpose": "primary_authentication",
        "auth_method": "password",
        "material": {"classification": "secret_fixture", "value": _VALUE},
    }
    binding.update(overrides)
    return binding


def _resolve(spec: dict, account_provider: str = provider.THEHIVE):
    resource = PlannedResource(
        address="provision.account-placement.console-admin",
        domain=RuntimeDomain.PROVISIONING,
        resource_type="account-placement",
        payload={"spec": spec},
    )
    return resolve_account_placement(
        resource=resource,
        payload={"spec": spec},
        target_address="provision.node.console",
        target_account_provider=account_provider,
    )


def _reason(diagnostics) -> str:
    assert len(diagnostics) == 1
    return diagnostics[0].message


def test_a_declared_fixture_credential_reaches_the_record_without_disclosure():
    account, diagnostics = _resolve(
        {
            "username": "admin@example.test",
            "node": "console",
            "password_strength": "weak",
            "credential_bindings": [_binding()],
        }
    )

    assert diagnostics == []
    assert account is not None
    assert account.credential is not None
    assert account.credential.credential_id == "console-primary"
    assert account.credential.value == _VALUE
    assert _VALUE not in repr(account)
    assert _VALUE not in str(account.details())
    assert account.details()["credential_id"] == "console-primary"


def test_a_key_credential_is_realized_only_by_a_key_capable_provider():
    spec = {
        "username": "sync-reader",
        "node": "console",
        "auth_method": "key",
        "credential_bindings": [_binding(auth_method="key")],
    }

    account, diagnostics = _resolve(spec, provider.MISP)
    assert diagnostics == []
    assert account is not None
    assert account.auth_method == "key"

    refused, diagnostics = _resolve(spec, provider.THEHIVE)
    assert refused is None
    assert "account-auth-method-unsupported" in _reason(diagnostics)


@pytest.mark.parametrize(
    ("bindings", "reason"),
    [
        (
            [
                _binding(
                    material={
                        "classification": "operator_secret",
                        "reference_id": "vault",
                    }
                )
            ],
            "account-credential-not-secret-fixture",
        ),
        ([_binding(), _binding(credential_id="second")], "bindings-unsupported"),
        ([_binding(purpose="recovery")], "account-credential-purpose-unsupported"),
        ([_binding(auth_method="key")], "account-credential-auth-method-mismatch"),
        (
            [_binding(material={"classification": "secret_fixture", "value": ""})],
            "account-credential-binding-invalid",
        ),
    ],
)
def test_an_unrealizable_binding_is_refused_not_substituted(bindings, reason):
    account, diagnostics = _resolve(
        {
            "username": "admin@example.test",
            "node": "console",
            "credential_bindings": bindings,
        }
    )

    assert account is None
    assert reason in _reason(diagnostics)


def test_an_application_provider_needs_a_declared_credential():
    account, diagnostics = _resolve(
        {"username": "admin@example.test", "node": "console"}
    )

    assert account is None
    assert "account-credential-required" in _reason(diagnostics)


def test_a_directory_account_without_a_binding_keeps_the_minted_path():
    account, diagnostics = _resolve(
        {"username": "jessica", "node": "ad", "password_strength": "weak"},
        provider.SAMBA_AD,
    )

    assert diagnostics == []
    assert account is not None
    assert account.credential is None


def test_a_target_without_an_account_provider_is_refused():
    account, diagnostics = _resolve(
        {"username": "admin@example.test", "credential_bindings": [_binding()]}, ""
    )

    assert account is None
    assert "no-account-provisioner-for-target" in _reason(diagnostics)


def _plan(spec):
    from raes_contracts.planning import ChangeAction, ProvisionOp, ProvisioningPlan

    return ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address="provision.account-placement.console-admin",
                resource_type="account-placement",
                payload={"spec": spec},
            )
        ]
    )


def test_a_credential_bearing_plan_returns_no_backend_details():
    """RAES accepts no free-form details from a credential-bearing apply (#1273)."""

    from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

    from aptl.backends.raes_provisioner import closed_credential_result

    result = ApplyResult(
        success=True, snapshot=RuntimeSnapshot(), details={"realization": {"x": 1}}
    )
    spec = {"username": "admin@example.test", "credential_bindings": [_binding()]}

    assert closed_credential_result(_plan(spec), result).details == {}
    assert closed_credential_result(_plan({"username": "u"}), result).details == {
        "realization": {"x": 1}
    }
