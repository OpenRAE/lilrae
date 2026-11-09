---
id: NET-003
title: "Multi-Network Container Attachment"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-03-20T06:09:24.291706Z
updated_at: 2026-03-20T06:18:11.648677Z
---

# NET-003: Multi-Network Container Attachment

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/NET-003/requirement.md).


## Statement

Containers that bridge network zones shall be attached to multiple Docker networks with a unique IP on each. Multi-homed containers include: Wazuh Manager (security, DMZ, internal), Kali (redteam, DMZ, internal), Suricata (security, DMZ, internal), DNS (security, DMZ, internal), web app (DMZ, internal), and mail server (DMZ, internal).

## Rationale

Multi-homing enables realistic service placement and attacker pivoting simulation.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-006-four-network-segmentation.md` (ADR-006: Four-Network Segmentation)
