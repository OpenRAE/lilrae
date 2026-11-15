---
id: INF-004
title: "Memory Limits for All Containers"
status: ACTIVE
type: NON_FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-03-20T06:09:01.207689Z
updated_at: 2026-03-20T06:18:11.648546Z
---

# INF-004: Memory Limits for All Containers

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/INF-004/requirement.md).


## Statement

Every container shall declare a memory limit (deploy.resources.limits.memory) to prevent resource starvation. Limits range from 128MB (DNS, Redis) to 2GB (Wazuh Indexer) based on observed usage.

## Rationale

Without memory limits, a single container can consume all available host memory, causing OOM kills across the entire lab.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-005-docker-compose-profiles.md` (ADR-005: Docker Compose Profiles)
