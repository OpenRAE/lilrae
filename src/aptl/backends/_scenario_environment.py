"""Environment contracts shared by scenario startup adapter validation."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field

from aptl.core.deployment.realization import valid_environment_variable_name


class ScenarioStartupProviderError(RuntimeError):
    """Stable fail-closed diagnostic for the scenario-startup adapter seam."""


@dataclass(frozen=True, order=True)
class EnvironmentAlias:
    """Copy one existing operator credential to a runtime variable name."""

    target: str
    source: str


@dataclass(frozen=True, order=True)
class ScenarioEnvironmentFixture:
    """One pack-fixed value projected into the local environment cache."""

    name: str
    value: str = field(repr=False, compare=False)


@dataclass(frozen=True, order=True)
class AccountCredentialFixture:
    """A startup variable whose value is one part of an SDL account credential.

    The adapter names the account and credential; core reads the username or
    the authored ``secret_fixture`` value from the admitted SDL. The adapter
    never holds the value, so a pack change to the credential reaches the
    environment without an adapter edit.
    """

    name: str
    account: str
    credential_id: str
    part: str


def resolved_environment_fixtures(
    value: object,
    accounts: Mapping[str, object] | None,
) -> object:
    """Replace each account reference with the authored value it names.

    ``accounts`` is the admitted SDL's account table, or ``None`` when no
    fixture references an account. A reference to anything but one authored
    ``secret_fixture`` refuses the plan.
    """

    from aptl.backends.raes_declared_credentials import (
        AccountCredentialReference,
        DeclaredCredentialError,
        resolve_declared_credential,
    )

    if not isinstance(value, tuple):
        return value
    resolved: list[object] = []
    for item in value:
        if not isinstance(item, AccountCredentialFixture):
            resolved.append(item)
            continue
        if accounts is None or item.part not in {"username", "secret"}:
            raise ScenarioStartupProviderError("provider-result-invalid")
        try:
            credential = resolve_declared_credential(
                accounts, AccountCredentialReference(item.account, item.credential_id)
            )
        except DeclaredCredentialError:
            raise ScenarioStartupProviderError("fixture-credential-unresolved") from None
        resolved.append(ScenarioEnvironmentFixture(item.name, credential.part(item.part)))
    return tuple(resolved)


def references_accounts(value: object) -> bool:
    """Return whether any startup fixture names an SDL account credential."""

    return isinstance(value, tuple) and any(
        isinstance(item, AccountCredentialFixture) for item in value
    )


def validated_aliases(value: object) -> tuple[EnvironmentAlias, ...]:
    """Validate unique, well-formed operator environment aliases."""

    if not isinstance(value, tuple):
        raise ScenarioStartupProviderError("provider-result-invalid")
    if any(not isinstance(item, EnvironmentAlias) for item in value):
        raise ScenarioStartupProviderError("provider-result-invalid")
    valid_names = all(
        valid_environment_variable_name(item.target)
        and valid_environment_variable_name(item.source)
        for item in value
    )
    unique_targets = len({item.target for item in value}) == len(value)
    if not valid_names or not unique_targets:
        raise ScenarioStartupProviderError("provider-result-invalid")
    return value


def validated_environment_fixtures(
    value: object, forbidden_names: Collection[str]
) -> tuple[ScenarioEnvironmentFixture, ...]:
    """Validate fixed values without copying their bytes into diagnostics."""

    if not isinstance(value, tuple):
        raise ScenarioStartupProviderError("provider-result-invalid")
    if any(not isinstance(item, ScenarioEnvironmentFixture) for item in value):
        raise ScenarioStartupProviderError("provider-result-invalid")
    names = [item.name for item in value]
    valid_names = all(
        valid_environment_variable_name(name) and name not in forbidden_names
        for name in names
    )
    valid_values = all(
        item.value and "\n" not in item.value and "\r" not in item.value
        for item in value
    )
    if len(names) != len(set(names)) or not valid_names or not valid_values:
        raise ScenarioStartupProviderError("provider-result-invalid")
    return value


__all__ = [
    "AccountCredentialFixture",
    "EnvironmentAlias",
    "ScenarioEnvironmentFixture",
    "ScenarioStartupProviderError",
    "references_accounts",
    "resolved_environment_fixtures",
    "validated_aliases",
    "validated_environment_fixtures",
]
