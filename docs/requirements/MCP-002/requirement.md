---
id: MCP-002
title: "Config-Driven Server Factory"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-03-20T06:11:54.699669Z
updated_at: 2026-03-20T06:18:11.649587Z
---

# MCP-002: Config-Driven Server Factory

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/MCP-002/requirement.md).


## Statement

Each MCP server shall be defined by a docker-lab-config.json file containing server metadata, connection details, SSH tool definitions, and API tool definitions. The createMCPServer() factory shall generate fully configured servers from this config without server-specific code.

## Rationale

Adding a new container to the MCP layer should require only a config file and a 4-line index.ts.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-003-mcp-common-library.md` (ADR-003: MCP Common Library)
