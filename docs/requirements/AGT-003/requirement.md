---
id: AGT-003
title: "Persistent Cross-Session Agent Memory"
status: DRAFT
type: FUNCTIONAL
priority: WONT
wave: 2
created_at: 2026-03-21T07:49:04.733391Z
updated_at: 2026-10-05T07:51:12.874346Z
---

# AGT-003: Persistent Cross-Session Agent Memory

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/AGT-003/requirement.md).


## Statement

The platform shall provide persistent agent memory that survives across sessions, storing discovered facts (credentials, network topology, host fingerprints, vulnerability findings) accessible to subsequent runs. ACES scope constraint (ADR-035 / SCN-010): discovered facts and environment state are owned by the ACES dynamic-knowledge / environment-state semantics (ACT-604, aces#212) and participant-consumable derived-context views (ACT-616, aces#250); memory shall be stored in / projected from those ACES contracts and read back via them, NOT a private APTL knowledge store that becomes a parallel source of truth. Dependency: blocked on ACES ACT-604 / ACT-616 (open/unbuilt upstream) and on the APTL AGT-001 orchestration layer to bind memory into.

## Rationale

WITHDRAWN 2026-10-05: No adopted scenario needs persistent participant memory. LilRAE participant control continues in #1216 and #1224. See GitHub issue #425. --- Original rationale: PentAGI uses long-term memory for multi-session campaigns. Without persistence, each run starts from zero, preventing cumulative learning and realistic multi-day adversary simulation.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#425` (AGT-003: Persistent Cross-Session Agent Memory)
