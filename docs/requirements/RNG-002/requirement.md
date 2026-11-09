---
id: RNG-002
title: "Multi-Node and Cloud Deployment"
status: DRAFT
type: NON_FUNCTIONAL
priority: WONT
wave: 3
created_at: 2026-03-21T07:50:13.382989Z
updated_at: 2026-10-05T07:51:12.874346Z
---

# RNG-002: Multi-Node and Cloud Deployment

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/RNG-002/requirement.md).


## Statement

The platform shall support deployment across multiple hosts and cloud environments, beyond the current single-host Docker Compose model, to enable scaling for larger topologies, concurrent users, and production-grade availability.

## Rationale

WITHDRAWN 2026-10-05: Multi-host cloud deployment, concurrent users and production availability are LilRAE non-goals. See GitHub issue #480. --- Original rationale: Single-host deployment limits scenario complexity, concurrent user count, and prevents realistic multi-segment network topologies. Academic ranges (KYPO, SPHERE) and military ranges (PCTE) all support multi-node deployment.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#480` (RNG-002: Multi-Node and Cloud Deployment)
