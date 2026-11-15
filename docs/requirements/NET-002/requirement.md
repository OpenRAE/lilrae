---
id: NET-002
title: "Static IP Addresses for All Containers"
status: ACTIVE
type: CONSTRAINT
priority: MUST
wave: 1
created_at: 2026-03-20T06:09:20.578789Z
updated_at: 2026-03-20T06:18:11.648655Z
---

# NET-002: Static IP Addresses for All Containers

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/NET-002/requirement.md).


## Statement

Every container shall have a fixed IPv4 address on each network it joins, assigned via ipv4_address in docker-compose.yml. IP allocation shall follow a consistent scheme: .10-.19 for infrastructure, .20-.29 for applications, .30-.39 for access points, .50 for Suricata.

## Rationale

Static IPs enable predictable addressing for MCP server configs, detection rules, and documentation.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-006-four-network-segmentation.md` (ADR-006: Four-Network Segmentation)
