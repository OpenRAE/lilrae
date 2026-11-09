---
id: INF-007
title: "Pre-Flight System Requirements Check"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 1
created_at: 2026-03-20T06:09:09.921003Z
updated_at: 2026-03-20T06:18:11.648611Z
---

# INF-007: Pre-Flight System Requirements Check

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/INF-007/requirement.md).


## Statement

The system shall validate host system requirements before deployment, including vm.max_map_count >= 262144 (required by OpenSearch/Elasticsearch), available Docker version, and Docker Compose version.

## Rationale

OpenSearch refuses to start when vm.max_map_count is too low, producing a cryptic error. Pre-flight checks fail early with a clear fix instruction.
