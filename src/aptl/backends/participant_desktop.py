"""Lazy adapter discovery for the participant desktop surface (issue #1273).

A scenario decides what its participant desktop shows: which consoles open, in
what order, which declared logins are listed, which guide is offered, and which
authored hostnames the browser must resolve. Core cannot know any of that
generically, so a pack-bound provider answers it through the
``aptl.participant_desktop`` entry-point group.

The provider returns references only: SDL node and service names, SDL account
and credential ids, and a bundle-relative asset path. It never returns a URL,
an address, a hostname, or a credential value. Core resolves every reference
against the admitted SDL and the realized lab
(:mod:`aptl.core.participant_desktop`), so a pack change reaches the desktop
without an adapter edit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import metadata
from pathlib import PurePosixPath
from typing import TypeVar

from aptl.core.scenario_bundle import ScenarioBundle
from aptl.utils.logging import get_logger

log = get_logger("participant-desktop")

ENTRY_POINT_GROUP = "aptl.participant_desktop"
EXTENSION_API_VERSION = "1"

_SDL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._()/-]{0,63}")
_MAX_ITEMS = 32
_Item = TypeVar("_Item")


class ParticipantDesktopProviderError(RuntimeError):
    """Stable fail-closed diagnostic for the participant desktop seam."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DesktopConsole:
    """A console the desktop opens: an SDL node's named service."""

    label: str
    node: str
    service: str


@dataclass(frozen=True)
class DesktopCredential:
    """A login the desktop lists: one credential an SDL account declares."""

    label: str
    account: str
    credential_id: str


@dataclass(frozen=True)
class ParticipantDesktopSpec:
    """What one pack's participant desktop shows, as references."""

    consoles: tuple[DesktopConsole, ...] = ()
    credentials: tuple[DesktopCredential, ...] = ()
    guide: str | None = None
    hostnames: tuple[str, ...] = ()


def _entry_points() -> list[metadata.EntryPoint]:
    """Find installed providers without importing scenario-owned modules."""

    return list(metadata.entry_points(group=ENTRY_POINT_GROUP))


def _load(entry_point: metadata.EntryPoint) -> object:
    """Load one provider while converting import failures to stable errors."""

    try:
        provider = entry_point.load()
        if isinstance(provider, type):
            provider = provider()
    except Exception as exc:
        log.warning(
            "participant desktop provider load failed: selector=%s exception=%s",
            entry_point.name,
            type(exc).__name__,
        )
        raise ParticipantDesktopProviderError("provider-load-failed") from None
    return provider


def _compatible(provider: object, bundle: ScenarioBundle) -> bool:
    """Accept only providers bound to this exact pack release."""

    identity = bundle.pack_identity
    versions = getattr(provider, "supported_pack_versions", None)
    digests = getattr(provider, "supported_pack_set_digests", None)
    if (
        getattr(provider, "extension_api_version", None) != EXTENSION_API_VERSION
        or getattr(provider, "supported_pack_id", None) != identity.pack_id
        or not isinstance(versions, tuple)
        or not isinstance(digests, tuple)
        or any(
            not isinstance(value, str) or not value for value in (*versions, *digests)
        )
        or not callable(getattr(provider, "resolve", None))
    ):
        raise ParticipantDesktopProviderError("provider-malformed")
    return identity.pack_version in versions and identity.set_digest in digests


def _bounded(items: object, kind: type[_Item]) -> tuple[_Item, ...]:
    """Return a bounded tuple whose every item is ``kind``, or refuse."""

    if not isinstance(items, tuple) or len(items) > _MAX_ITEMS:
        raise ParticipantDesktopProviderError("provider-result-invalid")
    if any(not isinstance(item, kind) for item in items):
        raise ParticipantDesktopProviderError("provider-result-invalid")
    return items


def _valid_guide(value: object) -> bool:
    """Accept a bounded, contained, bundle-relative asset path."""

    if not isinstance(value, str) or not value or len(value) > 256:
        return False
    path = PurePosixPath(value)
    return (
        bool(path.parts)
        and not path.is_absolute()
        and all(_SDL_ID.fullmatch(part) for part in path.parts)
    )


def validated_spec(value: object) -> ParticipantDesktopSpec:
    """Copy a provider result after validating every reference's shape."""

    if not isinstance(value, ParticipantDesktopSpec):
        raise ParticipantDesktopProviderError("provider-result-invalid")
    consoles = _bounded(value.consoles, DesktopConsole)
    credentials = _bounded(value.credentials, DesktopCredential)
    hostnames = _bounded(value.hostnames, str)
    labels = [item.label for item in (*consoles, *credentials)]
    identifiers = [
        *(part for item in consoles for part in (item.node, item.service)),
        *(part for item in credentials for part in (item.account, item.credential_id)),
        *hostnames,
    ]
    if (
        not _valid_references(labels, identifiers)
        or not _unique_labels(consoles)
        or not _unique_labels(credentials)
        or len(set(hostnames)) != len(hostnames)
        or (value.guide is not None and not _valid_guide(value.guide))
    ):
        raise ParticipantDesktopProviderError("provider-result-invalid")
    return ParticipantDesktopSpec(
        consoles=tuple(
            DesktopConsole(item.label, item.node, item.service) for item in consoles
        ),
        credentials=tuple(
            DesktopCredential(item.label, item.account, item.credential_id)
            for item in credentials
        ),
        guide=value.guide,
        hostnames=tuple(hostnames),
    )


def _unique_labels(items: tuple[DesktopConsole | DesktopCredential, ...]) -> bool:
    """Require each reference category to name unique display labels."""

    return len({item.label for item in items}) == len(items)


def _valid_references(labels: list[object], identifiers: list[object]) -> bool:
    """Validate display text and SDL identifier grammars separately."""

    return all(
        isinstance(label, str) and _LABEL.fullmatch(label) for label in labels
    ) and all(isinstance(part, str) and _SDL_ID.fullmatch(part) for part in identifiers)


def select_participant_desktop(
    bundle: ScenarioBundle, *, required: bool = False
) -> ParticipantDesktopSpec | None:
    """Return the exact pack's desktop references, or ``None`` when it has none.

    A pack with no provider has no desktop surface; that is not an error. A
    provider that is present but ambiguous, malformed, or failing refuses.
    """

    identity = bundle.pack_identity
    if identity is None:
        if required:
            raise ParticipantDesktopProviderError("provider-missing")
        return None
    candidates = [
        entry_point
        for entry_point in _entry_points()
        if entry_point.name == identity.pack_id
    ]
    compatible = []
    for entry_point in candidates:
        provider = _load(entry_point)
        if _compatible(provider, bundle):
            compatible.append((entry_point, provider))
    if len(compatible) > 1:
        raise ParticipantDesktopProviderError("provider-ambiguous")
    if not compatible:
        if candidates:
            raise ParticipantDesktopProviderError("provider-incompatible")
        if required:
            raise ParticipantDesktopProviderError("provider-missing")
        return None
    try:
        entry_point, provider = compatible[0]
        result = validated_spec(provider.resolve(bundle))
        distribution = getattr(entry_point, "dist", None)
        log.info(
            "participant desktop selected: pack=%s distribution=%s version=%s entry_point=%s",
            identity.pack_id,
            getattr(distribution, "name", "unavailable"),
            getattr(distribution, "version", "unavailable"),
            entry_point.name,
        )
        return result
    except ParticipantDesktopProviderError:
        raise
    except Exception as exc:
        log.warning(
            "participant desktop provider resolve failed: selector=%s exception=%s",
            identity.pack_id,
            type(exc).__name__,
        )
        raise ParticipantDesktopProviderError("provider-resolve-failed") from None


__all__ = (
    "ENTRY_POINT_GROUP",
    "EXTENSION_API_VERSION",
    "DesktopConsole",
    "DesktopCredential",
    "ParticipantDesktopProviderError",
    "ParticipantDesktopSpec",
    "select_participant_desktop",
    "validated_spec",
)
