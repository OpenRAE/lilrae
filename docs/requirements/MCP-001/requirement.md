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

## Statement

The system shall provide one shared MCP runtime that all MCP servers use. It shall provide persistent SSH sessions, SSH connection pooling, an HTTP client for API access, a configuration-driven server factory, one server entry point, typed tool arguments, and shell output formatting.

## Rationale

Without a common library, each MCP server duplicated SSH handling producing copy-paste bugs.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-003-mcp-common-library.md` (ADR-003: MCP Common Library)
- IMPLEMENTS → CODE_FILE `mcp/aptl-mcp-common/src/server.ts` (MCP server factory)
