---
id: ENT-007
title: "Internal BIND9 DNS Server"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 3
created_at: 2026-03-20T06:11:20.616177Z
updated_at: 2026-03-20T06:18:11.649416Z
---

# ENT-007: Internal BIND9 DNS Server

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/ENT-007/requirement.md).


## Statement

The system shall provide a BIND9 DNS server resolving the techvault.local zone, attached to security, DMZ, and internal networks for cross-zone name resolution.

## Rationale

DNS is a core enterprise service and also represents an exfiltration vector.
