---
id: SAF-003
title: "Tiered Autonomy Levels"
status: DRAFT
type: FUNCTIONAL
priority: WONT
wave: 2
created_at: 2026-03-21T07:50:57.939809Z
updated_at: 2026-10-05T07:51:12.874346Z
---

# SAF-003: Tiered Autonomy Levels

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SAF-003/requirement.md).


## Statement

The platform shall support configurable autonomy tiers for agent operations: observe (read-only reconnaissance), investigate (non-destructive queries and analysis), execute (run pre-approved actions with confirmation), and autonomous (full independent operation within safety bounds).

## Rationale

WITHDRAWN 2026-10-05: Tiered autonomy includes confirmation of actions, which is approval gating. SAF-006 withdrew approval gating. Containment is the perimeter (SAF-002, NET-005). See GitHub issue #455. --- Original rationale: NVIDIA recommends tiered isolation. Different use cases (training, research, benchmarking) require different levels of agent freedom. One-size-fits-all autonomy is either too restrictive or too dangerous.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#455` (SAF-003: Tiered Autonomy Levels)
