---
id: INT-006
title: "Cortex MCP Server"
status: DRAFT
type: FUNCTIONAL
priority: WONT
wave: 3
created_at: 2026-03-21T07:52:07.965122Z
updated_at: 2026-10-09T00:00:00.000000Z
---

# INT-006: Cortex MCP Server

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/INT-006/requirement.md).


## Statement

The platform shall provide an MCP server for Cortex (SOC-004), exposing observable enrichment capabilities (IP, domain, hash, email analysis) to AI agents via standard MCP tool calls.

## Rationale

WITHDRAWN 2026-10-09: The issue closed as not planned on 2026-07-19 without a closing comment. See GitHub issue #474. --- Original rationale: Cortex is deployed (SOC-004) but has no MCP server, making it the only SOC tool inaccessible to AI agents. Adding an MCP server completes the SOC tool coverage.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#474` (INT-006: Cortex MCP Server)
