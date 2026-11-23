---
id: SAF-004
title: "MCP Command Filtering (Allowlist/Denylist, Rate Limiting)"
status: DRAFT
type: FUNCTIONAL
priority: WONT
wave: 2
created_at: 2026-03-21T07:51:02.052417Z
updated_at: 2026-10-05T07:51:12.874346Z
---

# SAF-004: MCP Command Filtering (Allowlist/Denylist, Rate Limiting)

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SAF-004/requirement.md).


## Statement

The MCP layer shall support configurable command filtering: per-server allowlists and denylists for tool invocations, and rate limiting to prevent runaway agent behavior (for example, infinite loop of destructive commands).

## Rationale

WITHDRAWN 2026-10-05: Command filtering of in-range agent actions conflicts with the perimeter containment model (SAF-002, NET-005). #967 covers argument validation. See GitHub issue #456. --- Original rationale: MCP servers currently execute any valid tool call without restriction. Command filtering provides defense-in-depth for autonomous agent operations, complementing the kill switch and tiered autonomy.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#456` (SAF-004: MCP Command Filtering (Allowlist/Denylist, Rate Limiting))
