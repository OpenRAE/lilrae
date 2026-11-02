"""The one TechVault pack release this adapter is qualified against.

Every TechVault surface in this package reads this pair. The module imports
nothing, so a surface that must load without the RAES runtime installed (the
scenario verifier) can still read it.
"""

from __future__ import annotations

#: Exact content identity of the TechVault pack this release qualified, as
#: ``raes-env-packs`` admits it through ``env_pack_bundle()``. A pack release
#: that changes these bytes is a pack this adapter has not been qualified
#: against, and it takes an adapter release -- not a wider declaration -- to
#: admit one. Every TechVault surface in this package reads this one pair.
TECHVAULT_PACK_SET_DIGEST = (
    "sha256:3a7706c8b20bd1a052017f67a77f5316ea8b16530015baa48278f3f64f52c600"
)
#: The pack release these bytes belong to. Version and digest form one pair:
#: a release qualifies content, not a version number that content might later
#: change under.
TECHVAULT_PACK_VERSION = "7.2.0"


__all__ = ("TECHVAULT_PACK_SET_DIGEST", "TECHVAULT_PACK_VERSION")
