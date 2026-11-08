---
id: ORC-004
title: "Agent-to-Agent Communication and Shared Context"
status: DRAFT
type: FUNCTIONAL
priority: WONT
wave: 2
created_at: 2026-03-21T07:51:24.830558Z
updated_at: 2026-10-05T07:51:12.874346Z
---

# ORC-004: Agent-to-Agent Communication and Shared Context

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/ORC-004/requirement.md).


## Statement

The platform shall provide a mechanism for multiple agents to communicate findings and share context (for example, red agent shares discovered credentials with a lateral movement specialist, or blue agent alerts red agent's observer about a detection). ACES scope constraint (ADR-035 / SCN-010): inter-participant shared context is owned by the ACES shared-operational-state / derived-context contract (API-410, aces#253) and multi-participant coordination & delegation (ACT-612, aces#214); shared context shall flow through those contracts, NOT a bespoke APTL inter-agent bus that becomes a parallel source of truth. Sub-capability of multi-agent coordination, subordinate to AGT-002. Dependency: blocked on ACES API-410 / ACT-612 (open/unbuilt upstream).

## Rationale

WITHDRAWN 2026-10-05: No adopted scenario needs shared participant context. See GitHub issue #450. --- Original rationale: Multi-agent operation (AGT-002) requires inter-agent communication. Without shared context, agents duplicate work and cannot coordinate strategies across specializations.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#450` (ORC-004: Agent-to-Agent Communication and Shared Context)
