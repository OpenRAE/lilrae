---
id: MCP-001
title: "Shared MCP Server Library"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-03-20T06:11:51.226199Z
updated_at: 2026-03-20T06:18:11.649566Z
---

# MCP-001: Shared MCP Server Library

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/MCP-001/requirement.md).


## Statement

The system shall provide one shared MCP runtime that all MCP servers use. It shall provide persistent SSH sessions, SSH connection pooling, an HTTP client for API access, a configuration-driven server factory, one server entry point, typed tool arguments, and shell output formatting.

## Rationale

Without a common library, each MCP server duplicated SSH handling producing copy-paste bugs.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-003-mcp-common-library.md` (ADR-003: MCP Common Library)
- IMPLEMENTS → CODE_FILE `mcp/aptl-mcp-common/src/server.ts` (MCP server factory)
