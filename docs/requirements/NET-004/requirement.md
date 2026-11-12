---
id: NET-004
title: "Internal DNS for Cross-Zone Resolution"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 1
created_at: 2026-03-20T06:09:26.893568Z
updated_at: 2026-03-20T06:18:11.648724Z
---

# NET-004: Internal DNS for Cross-Zone Resolution

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/NET-004/requirement.md).


## Statement

The system shall provide an internal DNS server (BIND9) that resolves techvault.local hostnames across all network zones, attached to security, DMZ, and internal networks.

## Rationale

Docker bridge networks prevent cross-network hostname resolution by default.
