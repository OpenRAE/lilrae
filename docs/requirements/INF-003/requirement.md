---
id: INF-003
title: "Health Checks for All Containers"
status: ACTIVE
type: NON_FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-03-20T06:08:57.534805Z
updated_at: 2026-03-20T06:18:11.648524Z
---

# INF-003: Health Checks for All Containers

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/INF-003/requirement.md).


## Statement

Every container shall define a Docker health check with appropriate start_period (120-300s for SOC tools), interval, timeout, and retry parameters tuned to observed cold-start times.

## Rationale

Health checks enable dependency-aware startup ordering and allow the CLI orchestrator to determine when services are ready before proceeding.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-005-docker-compose-profiles.md` (ADR-005: Docker Compose Profiles)
