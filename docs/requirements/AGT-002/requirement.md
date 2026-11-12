---
id: AGT-002
title: "ACES-Aligned Multi-Agent Coordination"
status: DRAFT
type: FUNCTIONAL
priority: WONT
wave: 2
created_at: 2026-03-21T07:49:00.755641Z
updated_at: 2026-10-05T07:51:12.874346Z
---

# AGT-002: ACES-Aligned Multi-Agent Coordination

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/AGT-002/requirement.md).


## Statement

The platform shall support concurrent operation of multiple ACES-declared participants or agents - at minimum red and blue roles - with a purple-team coordinator that observes portable workflow/evaluation state, records coordination events, and measures detection/response coverage without using APTL-private participant semantics as the source of truth.

## Rationale

WITHDRAWN 2026-10-05: No adopted scenario needs multi-participant coordination. RAES owns the semantics (ACT-612). Multi-role participant runs already work through #557. LilRAE participant control continues in #1216 and #1224. See GitHub issue #420. --- Original rationale: Purple-team research still requires simultaneous offense and defense, but the coordination model must be layered on ACES participant and runtime contracts. Moving this out of Wave 1 avoids treating broad multi-agent behavior as a prerequisite for the TechVault authoring cutover.

## Traceability

- DOCUMENTS → DOCUMENTATION `docs/architecture/issue-420-concurrent-participants-preflight.md` (Distinguishes reopened issue scope from this withdrawn coordinator requirement)
