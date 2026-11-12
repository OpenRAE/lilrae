---
id: INF-002
title: "Profile-Based Selective Deployment"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-03-20T06:08:53.928647Z
updated_at: 2026-03-20T06:18:11.648501Z
---

# INF-002: Profile-Based Selective Deployment

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/INF-002/requirement.md).


## Statement

The system shall support selective deployment of container subsets via Docker Compose profiles, controlled by an aptl.json configuration file. Profile groups shall include: wazuh, victim, kali, reverse, soc, and enterprise.

## Rationale

The full stack (19+ containers) requires ~20GB RAM. Selective deployment enables use on resource-constrained machines and allows users to run only containers relevant to their current task.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-005-docker-compose-profiles.md` (ADR-005: Docker Compose Profiles)
- IMPLEMENTS → CONFIG `aptl.json` (Lab profile configuration)
