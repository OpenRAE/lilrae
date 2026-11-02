"""Reviewed source and compiled identities of the bounded-agency freeze.

The bounded participant driver admits its privileged action registry only for
an authored scenario whose source and compiled model match these reviewed
digests.
"""

from __future__ import annotations

BOUNDED_PARTICIPANT_AGENCY_SOURCE_SHA256 = (
    "cdd16c1bb18c0e281030137719bf88f7a8df9c7f0b6288de28e4355501942252"
)
#: Reviewed compiled models of the unchanged authored freeze, one for each
#: RAES release in the supported range that compiles it differently. raes
#: 10.0.0 compiles the freeze to the model that raes 9.2.0 compiled. A new
#: compiled model fails closed until reviewed.
BOUNDED_PARTICIPANT_AGENCY_COMPILED_SHA256S = frozenset(
    {
        # raes 10.0.0
        "31539407a07892bd106d502b95aea256c97ed107eef411c45b298ca3a3c2a3a5",
    }
)

__all__ = (
    "BOUNDED_PARTICIPANT_AGENCY_COMPILED_SHA256S",
    "BOUNDED_PARTICIPANT_AGENCY_SOURCE_SHA256",
)
