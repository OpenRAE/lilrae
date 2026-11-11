---
id: AGT-005
title: "Autonomous Objective Pursuit"
status: DRAFT
type: FUNCTIONAL
priority: WONT
wave: 3
created_at: 2026-03-21T07:49:11.494950Z
updated_at: 2026-10-05T07:51:12.874346Z
---

# AGT-005: Autonomous Objective Pursuit

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/AGT-005/requirement.md).


## Statement

The platform shall enable agents to autonomously evaluate and work toward scenario objectives without manual intervention, using objectives as goal states that drive planning and action selection. ACES scope constraint (ADR-035 / SCN-010): objective definitions, completion state, scoring, and outcomes are owned by the ACES participant outcome model (ACT-618, aces#218) and the ACES agent-evaluation-loop semantics (aces#171, aces#175); this requirement shall consume those contracts and shall NOT introduce a second, APTL-private objective-semantics or scoring layer. Dependency: blocked on ACES ACT-618 and the evaluation-loop semantics, which are open/unbuilt upstream. This requirement is downstream-dependent and not yet buildable.

## Rationale

WITHDRAWN 2026-10-05: Pursuit of objectives is a property of the participant, not of the backend. The backend part (run participants, record actions and outcomes) is complete through #557. See GitHub issue #463. --- Original rationale: Objectives currently exist only for manual post-hoc evaluation (SCN-007). Wiring them into the agent loop enables autonomous goal-directed behavior, a prerequisite for benchmarking agent performance.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#463` (AGT-005: Autonomous Objective Pursuit)
