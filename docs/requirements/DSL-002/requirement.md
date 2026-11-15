---
id: DSL-002
title: "Control Flow Primitives in Scenario DSL"
status: DEPRECATED
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-03-21T07:52:23.625763Z
updated_at: 2026-05-19T05:13:24.200961Z
---

# DSL-002: Control Flow Primitives in Scenario DSL

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/DSL-002/requirement.md).


## Statement

The scenario DSL shall support control flow primitives: conditionals (if/else based on action outcomes), branching (parallel attack paths), loops (retry with variations), error recovery handlers, and parallel execution of independent steps.

## Rationale

Current scenarios are linear sequences of hardcoded commands. Real attacks involve branching decisions, parallel operations, and error handling. CACAO v2.0 supports if-condition, while-condition, switch-condition, and parallel step types.

## Traceability

- DOCUMENTS → ADR `docs/adrs/adr-018-control-flow-primitives.md` (ADR-018: Control Flow Primitives in the SDL)
