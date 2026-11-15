---
id: RNG-005
title: "C2 Framework Integration"
status: DRAFT
type: FUNCTIONAL
priority: WONT
wave: 2
created_at: 2026-03-21T07:50:24.528016Z
updated_at: 2026-10-05T07:51:12.874346Z
---

# RNG-005: C2 Framework Integration

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/RNG-005/requirement.md).


## Statement

The lab shall include a command-and-control framework (for example, Mythic, Sliver, or equivalent) with an associated MCP server, enabling realistic adversary simulation with implant deployment, beacon management, and post-exploitation workflows.

## Rationale

WITHDRAWN 2026-10-05: A C2 server that a pack declares is an ordinary node. No pack needs a separate C2 capability. See GitHub issue #454. --- Original rationale: Real adversaries use C2 frameworks. Without C2, red team exercises are limited to manual command execution. Mythic and Sliver are open-source, well-documented, and widely used in professional red team operations.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#454` (RNG-005: C2 Framework Integration)
