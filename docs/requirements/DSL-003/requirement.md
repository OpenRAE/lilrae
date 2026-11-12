---
id: DSL-003
title: "Variable System and Runtime Substitution"
status: DEPRECATED
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-03-21T07:52:28.159023Z
updated_at: 2026-10-09T00:00:00.000000Z
---

# DSL-003: Variable System and Runtime Substitution

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/DSL-003/requirement.md).


## Statement

The scenario DSL shall support a variable system with: static parameters (configurable at launch), fact-based substitution (variables resolved from discovered runtime state like IPs, credentials, hostnames), and scoped variable namespaces.

## Rationale

DEPRECATED 2026-10-09: ADR-035 deprecates DSL-002 to DSL-009. #432 delivered the LilRAE side (PR #798): LilRAE accepts per-run variable bindings, RAES validates and substitutes them, and the admitted plan runs without local SDL reinterpretation. The issue closed as completed on 2026-07-18. See GitHub issue #432. --- Original rationale: Without variables, every scenario is hardcoded to specific IPs, credentials, and paths. CALDERA's fact store and Atomic Red Team's input_arguments demonstrate that parameterization is standard. Variables enable scenario reuse across different range configurations.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#432` (DSL-003: Variable System and Runtime Substitution)
