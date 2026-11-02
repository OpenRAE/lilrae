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
    "sha256:27b268a772189c7a6828b78233bba45c7ad568b8c55bfa6a841be257637ae1e5"
)
#: The pack release these bytes belong to. Version and digest form one pair:
#: a release qualifies content, not a version number that content might later
#: change under.
TECHVAULT_PACK_VERSION = "7.2.1"


__all__ = ("TECHVAULT_PACK_SET_DIGEST", "TECHVAULT_PACK_VERSION")

STUDY_PACK_SET_DIGEST = (
    "sha256:4aa2070905cf87428de97ce2b237d22857db9607f052c13b48b27fd8bf4d551a"
)
