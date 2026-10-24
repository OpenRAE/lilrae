"""Resolve RAES account-placement payloads into typed realization records.

An `account-placement` resource lowers into a typed
:class:`DeploymentAccountRealization` here, or fails closed with an error
diagnostic when its target node has no registered account provider. This is the
interpret-time half of account realization: #577 (ADR-046 Account and Identity
Realization Addendum) makes the record load-bearing — the deployment backend's
``realize_accounts`` operation ensures the declared groups, users, memberships,
and non-secret attributes on the resolved target and verifies them by
read-after-write. A minted credential is generated inside the target/provider
boundary and never crosses this record (ADR-029); an authored ``secret_fixture``
binding is lowered into the record's ``credential`` outside its evidence
projection (ADR-046 Declared Fixture Credential Addendum). The account provider
is the one the node's backend implementation names, and the set of known
providers is owned by :mod:`aptl.core.deployment._account_provider`, so this
gate and the materializer never diverge.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import PlannedResource

from aptl.backends.raes_diagnostics import diagnostic
from aptl.backends.raes_realization_values import (
    account_groups as _account_groups,
    optional_bool as _optional_bool,
    optional_string as _optional_string,
    placement_spec as _placement_spec,
)
from aptl.core.deployment._account_credentials import (
    DEFAULT_PASSWORD_STRENGTH,
    REALIZABLE_PASSWORD_STRENGTHS,
)
from aptl.core.deployment._account_provider import (
    KEY_AUTH_PROVIDERS,
    REQUIRES_DECLARED_CREDENTIAL,
    known_account_provider,
)
from aptl.core.deployment.realization import (
    DeclaredAccountCredential,
    DeploymentAccountRealization,
)

_PRIMARY_PURPOSE = "primary_authentication"
_SECRET_FIXTURE = "secret_fixture"
_PASSWORD = "password"


def resolve_account_placement(
    *,
    resource: PlannedResource,
    payload: Mapping[str, Any],
    target_address: str,
    target_account_provider: str | None,
) -> tuple[DeploymentAccountRealization | None, list[Diagnostic]]:
    """Lower one account-placement resource or return fail-closed diagnostics."""

    spec = _placement_spec(payload)
    username = _optional_string(spec, "username") if spec is not None else None
    strength = _declared_strength(spec)
    reason = _account_placement_rejection(
        spec, username, target_account_provider, strength
    )
    credential: DeclaredAccountCredential | None = None
    auth_method = _declared_auth_method(spec)
    if reason is None:
        credential, reason = _declared_credential(spec, auth_method)
    if reason is None:
        reason = _provider_credential_rejection(
            target_account_provider, auth_method, credential
        )

    account: DeploymentAccountRealization | None = None
    diagnostics: list[Diagnostic] = []
    if reason is not None:
        diagnostics = [_reject(resource.address, reason)]
    else:
        account = DeploymentAccountRealization(
            address=resource.address,
            target_address=target_address,
            username=username,
            groups=_account_groups(spec),
            spn=_optional_string(spec, "spn") or "",
            mail=_optional_string(spec, "mail") or "",
            # Preserve author explicitness (SEM-218, ADR-046 addendum): None when
            # the author omitted `disabled`, so the backend never flips an
            # existing account's enabled state on an unrelated placement.
            disabled=_optional_bool(spec, "disabled"),
            password_strength=strength,
            auth_method=auth_method,
            credential=credential,
        )
    return account, diagnostics


def _declared_strength(spec: Mapping[str, Any] | None) -> str:
    """Return the authored credential class, or RAES's own default.

    RAES defaults ``Account.password_strength`` to ``medium``, so an absent key
    is an authored medium account, not an unrealizable one. A present but
    unrecognized value is a different matter and is refused below.
    """

    if spec is None:
        return ""
    raw = _optional_string(spec, "password_strength")
    if raw is None or not raw.strip():
        return DEFAULT_PASSWORD_STRENGTH
    return raw.strip().lower()


def _account_placement_rejection(
    spec: Mapping[str, Any] | None,
    username: str | None,
    target_account_provider: str | None,
    strength: str,
) -> str | None:
    """Return the first fail-closed rejection reason for an account placement.

    None means the placement passed every policy check.
    """

    reason = None
    if spec is None:
        reason = "invalid-account-spec"
    elif username is None:
        reason = "account-missing-username"
    elif not known_account_provider(target_account_provider):
        reason = "no-account-provisioner-for-target"
    elif strength not in REALIZABLE_PASSWORD_STRENGTHS:
        # An authored credential class this backend cannot realize is refused
        # here rather than quietly realized as something else. A `weak` account
        # realized with a random password is a different environment than the
        # one the scenario declares (issue #1006).
        reason = "account-password-strength-unrealizable"
    return reason


def _declared_auth_method(spec: Mapping[str, Any] | None) -> str:
    """Return the authored account auth method, or RAES's ``password`` default."""

    raw = _optional_string(spec, "auth_method") if spec is not None else None
    return raw.strip().lower() if raw is not None else _PASSWORD


def _declared_credential(
    spec: Mapping[str, Any] | None,
    auth_method: str,
) -> tuple[DeclaredAccountCredential | None, str | None]:
    """Lower the one credential binding a provider can realize, or refuse.

    An account with no binding keeps the minted-credential path. A binding is
    realized only when it is the single primary credential, uses the account's
    own auth method, and carries authored ``secret_fixture`` material. An
    ``operator_secret`` binding names a value APTL has no source for, so it is
    refused rather than realized with something else.
    """

    bindings = spec.get("credential_bindings") if spec is not None else None
    if not bindings:
        return None, None
    if not isinstance(bindings, list) or len(bindings) != 1:
        return None, "account-credential-bindings-unsupported"
    return _credential_binding(bindings[0], auth_method)


def _credential_binding(
    binding: object, auth_method: str
) -> tuple[DeclaredAccountCredential | None, str | None]:
    """Validate one primary fixture independently of batch cardinality."""

    material = binding.get("material") if isinstance(binding, Mapping) else None
    if not isinstance(material, Mapping):
        return None, "account-credential-binding-invalid"
    reason = _binding_rejection(binding, material, auth_method)
    value = material.get("value")
    credential_id = binding.get("credential_id")
    if reason is None and not (
        isinstance(value, str) and value and isinstance(credential_id, str)
    ):
        reason = "account-credential-binding-invalid"
    result = (
        None
        if reason
        else DeclaredAccountCredential(credential_id=credential_id, value=value)
    )
    return result, reason


def _binding_rejection(
    binding: Mapping[str, Any], material: Mapping[str, Any], auth_method: str
) -> str | None:
    """Require the declared classification, purpose and authentication method."""

    reason = None
    if material.get("classification") != _SECRET_FIXTURE:
        reason = "account-credential-not-secret-fixture"
    elif binding.get("purpose") != _PRIMARY_PURPOSE:
        reason = "account-credential-purpose-unsupported"
    elif str(binding.get("auth_method") or _PASSWORD).lower() != auth_method:
        reason = "account-credential-auth-method-mismatch"
    return reason


def _provider_credential_rejection(
    provider: str | None,
    auth_method: str,
    credential: DeclaredAccountCredential | None,
) -> str | None:
    """Refuse a credential shape the selected provider cannot realize."""

    if auth_method != _PASSWORD and provider not in KEY_AUTH_PROVIDERS:
        return "account-auth-method-unsupported"
    if credential is None and provider in REQUIRES_DECLARED_CREDENTIAL:
        return "account-credential-required"
    return None


def _reject(address: str, reason_code: str) -> Diagnostic:
    """Build a fail-closed account realization diagnostic."""

    return diagnostic(
        "aptl.provisioner.account-placement-rejected",
        address,
        (
            "RAES account placement was rejected by the APTL account "
            f"realization policy (reason={reason_code})."
        ),
    )
