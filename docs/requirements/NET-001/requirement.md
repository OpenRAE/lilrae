---
id: NET-001
title: "Four Docker Bridge Networks"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-03-20T06:09:16.688302Z
updated_at: 2026-03-20T06:18:11.648633Z
---

# NET-001: Four Docker Bridge Networks

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/NET-001/requirement.md).


## Statement

The system shall define four Docker bridge networks: Security (172.20.0.0/24) for SOC tools, DMZ (172.20.1.0/24) for externally reachable services, Internal (172.20.2.0/24) for enterprise services, and Red Team (172.20.4.0/24) for the attack platform.

## Rationale

Four zones model the standard enterprise network architecture that security practitioners need to understand.

## Traceability

- IMPLEMENTS → CONFIG `docker-compose.yml` (Docker Compose network definitions)
- IMPLEMENTS → ADR `docs/adrs/adr-006-four-network-segmentation.md` (ADR-006: Four-Network Segmentation)
