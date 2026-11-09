---
id: NET-005
title: "Zone Isolation via Multi-Homing Only"
status: ACTIVE
type: CONSTRAINT
priority: MUST
wave: 1
created_at: 2026-03-20T06:09:30.552320Z
updated_at: 2026-03-20T06:18:11.648754Z
---

# NET-005: Zone Isolation via Multi-Homing Only

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/NET-005/requirement.md).


## Statement

Containers on different Docker networks shall be unable to communicate directly. Inter-zone communication shall only be possible through multi-homed containers that bridge network boundaries.

## Rationale

Docker bridge isolation provides zone boundaries without external firewall appliances. A compromised multi-homed container provides a real lateral movement path.

## Traceability

- CONSTRAINS → ADR `docs/adrs/adr-006-four-network-segmentation.md` (ADR-006: Four-Network Segmentation)
