---
id: MCP-004
title: "SSH MCP Servers for Container Access"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-03-20T06:12:02.801120Z
updated_at: 2026-03-20T06:18:11.649629Z
---

# MCP-004: SSH MCP Servers for Container Access

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/MCP-004/requirement.md).


## Statement

The system shall provide SSH-based MCP servers for direct container access: mcp-red (Kali), mcp-reverse (reverse engineering). These servers shall expose tools for command execution, session management, and file operations via persistent SSH sessions.

## Rationale

SSH-based servers provide interactive access where AI agents need to execute arbitrary commands.
