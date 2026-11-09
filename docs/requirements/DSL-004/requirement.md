---
id: DSL-004
title: "Scenario Composition (Atomic to Campaigns)"
status: DEPRECATED
type: FUNCTIONAL
priority: WONT
wave: 2
created_at: 2026-03-21T07:52:31.235076Z
updated_at: 2026-10-09T00:00:00.000000Z
---

# DSL-004: Scenario Composition (Atomic to Campaigns)

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/DSL-004/requirement.md).


## Statement

The scenario DSL shall support composition: combining atomic scenarios into campaigns, chains, or nested workflows, with reusable building blocks that can be referenced across exercises.

## Rationale

WITHDRAWN 2026-10-05: RAES owns scenario composition (rae#656). LilRAE realizes composed packs through #894 and #1239. See GitHub issue #433. --- Original rationale: Monolithic scenario files don't scale. Composition enables building complex campaigns from tested atomic units, sharing common patterns (for example, initial access, lateral movement) across different exercises.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#433` (DSL-004: Scenario Composition (Atomic to Campaigns))
