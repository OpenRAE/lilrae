"""Resolve SDL account credentials by reference, authored fixtures only (#1273).

A scenario adapter may name an account credential, never hold its value: it
says "this variable is the password of account X" and core reads the value from
the admitted SDL. Core resolves only an authored ``secret_fixture`` binding. An
``operator_secret`` binding, a missing or unknown reference, and an account
with several matching bindings are refused with a stable code, so no caller can
fall back to an ambient, ``.env``, or compatibility value.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

_SECRET_FIXTURE = "secret_fixture"

CredentialPart = Literal["username", "secret"]


class DeclaredCredentialError(ValueError):
    """A credential reference does not name one authored ``secret_fixture``."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DeclaredCredential:
    """One authored account credential and the principal it belongs to."""

    account: str
    credential_id: str
    username: str
    auth_method: str
    value: str = field(repr=False, compare=False)

    def part(self, part: CredentialPart) -> str:
        """Return the username or the secret value."""

        return self.username if part == "username" else self.value


@dataclass(frozen=True)
class AccountCredentialReference:
    """A reference to one credential an SDL account declares."""

    account: str
    credential_id: str


def scenario_accounts(sdl_path: Path) -> Mapping[str, object]:
    """Parse the admitted SDL and return its declared accounts by id."""

    from raes import parse_sdl_file

    return dict(getattr(parse_sdl_file(sdl_path), "accounts", {}) or {})


def resolve_declared_credential(
    accounts: Mapping[str, object],
    reference: AccountCredentialReference,
) -> DeclaredCredential:
    """Return the authored ``secret_fixture`` a reference names, or refuse."""

    account = accounts.get(reference.account)
    if account is None:
        raise DeclaredCredentialError("account-unknown")
    matches = [
        binding
        for binding in (getattr(account, "credential_bindings", None) or ())
        if getattr(binding, "credential_id", None) == reference.credential_id
    ]
    if len(matches) != 1:
        raise DeclaredCredentialError("credential-unknown")
    material = getattr(matches[0], "material", None)
    classification = _value(getattr(material, "classification", ""))
    value = getattr(material, "value", None)
    username = getattr(account, "username", None)
    if classification != _SECRET_FIXTURE:
        raise DeclaredCredentialError("credential-not-secret-fixture")
    if not (_single_line(value) and _single_line(username)):
        raise DeclaredCredentialError("credential-invalid")
    return DeclaredCredential(
        account=reference.account,
        credential_id=reference.credential_id,
        username=username,
        auth_method=_value(getattr(matches[0], "auth_method", "password")),
        value=value,
    )


def _value(raw: object) -> str:
    """Return an enum's value or a string, lower-cased."""

    return str(getattr(raw, "value", raw) or "").lower()


def _single_line(value: object) -> bool:
    """Return whether ``value`` is a non-empty single-line string."""

    return (
        isinstance(value, str)
        and bool(value)
        and not any(char in value for char in "\r\n\0")
    )


__all__ = (
    "AccountCredentialReference",
    "CredentialPart",
    "DeclaredCredential",
    "DeclaredCredentialError",
    "resolve_declared_credential",
    "scenario_accounts",
)
