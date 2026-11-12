---
id: MCP-006
title: "Typed MCP Tool Arguments"
status: ACTIVE
type: NON_FUNCTIONAL
priority: SHOULD
wave: 4
created_at: 2026-03-20T06:12:10.821388Z
updated_at: 2026-03-20T06:18:11.649672Z
---

# MCP-006: Typed MCP Tool Arguments

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/MCP-006/requirement.md).


## Statement

All MCP tool handlers shall receive named, typed argument structures instead of untyped maps. The runtime shall validate the arguments against the JSON Schema of the tool before the handler runs, and the typed structures add compile-time type checking.

## Rationale

any-typed args hid type errors until runtime. Named interfaces caught bugs during migration.

## Traceability

- IMPLEMENTS → CODE_FILE `mcp/aptl-mcp-common/src/tools/handlers.ts` (Typed tool argument interfaces)
- IMPLEMENTS → ADR `docs/adrs/adr-003-mcp-common-library.md` (ADR-003: MCP Common Library)
