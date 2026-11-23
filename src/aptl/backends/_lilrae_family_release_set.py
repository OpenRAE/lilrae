"""Consistent release set for one family trial (#1465).

The host and adapter requirements on these distributions must include each
installed version. An install without dependency resolution can otherwise mix
releases that the declarations exclude.
"""

from __future__ import annotations

from importlib import metadata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packaging.requirements import Requirement

_HOST_DISTRIBUTION = "lilrae"
_RELEASE_SET = frozenset({_HOST_DISTRIBUTION, "raes", "raes-env-packs"})


def require_consistent_release_set(adapter_requires: tuple[str, ...]) -> None:
    """Refuse installed releases that the host or adapter declarations exclude."""

    try:
        # Imported here so the family seam itself needs no third-party module.
        from packaging.requirements import Requirement

        declared = (*(metadata.requires(_HOST_DISTRIBUTION) or ()), *adapter_requires)
        if any(_excludes_installed_release(Requirement(text)) for text in declared):
            raise ValueError
    except Exception:
        raise ValueError("family-package-versions-inconsistent") from None


def _excludes_installed_release(requirement: Requirement) -> bool:
    """Return whether an applicable release-set requirement excludes its install."""

    from packaging.utils import canonicalize_name

    name = canonicalize_name(requirement.name)
    if name not in _RELEASE_SET:
        return False
    if requirement.marker is not None and not requirement.marker.evaluate(
        {"extra": ""}
    ):
        return False
    installed = metadata.version(name)
    return not requirement.specifier.contains(installed, prereleases=True)


__all__ = ["require_consistent_release_set"]
