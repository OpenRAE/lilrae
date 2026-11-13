---
id: SYS-007
title: "Model Context Protocol Server Layer"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-03-20T06:05:39.709305Z
updated_at: 2026-03-20T06:18:11.648412Z
---

# SYS-007: Model Context Protocol Server Layer

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SYS-007/requirement.md).


## Statement

The system shall expose all lab components (containers, SIEM, SOC tools) to AI agents via MCP (Model Context Protocol) servers, enabling programmatic attack execution, SIEM investigation, case management, and orchestration through standard MCP tool calls.

## Rationale

The core research purpose of APTL is studying how AI agents perform in attack-and-defense cycles. MCP provides the standard protocol for AI agent tool use, enabling any MCP-compatible agent to control the lab without custom integrations.
