---
id: MCP-003
title: "Stateful SSH Sessions with Command Queuing"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-03-20T06:11:59.691468Z
updated_at: 2026-03-20T06:18:11.649608Z
---

# MCP-003: Stateful SSH Sessions with Command Queuing

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/MCP-003/requirement.md).


## Statement

The system shall provide persistent SSH sessions that maintain shell state (environment variables, working directory, history) across multiple MCP tool calls. Sessions shall use delimiter-based output parsing, FIFO command queuing, per-command timeouts, 10,000-line buffer overflow protection, and 30-second keepalive.

## Rationale

Per-command SSH connections have 200-500ms latency overhead, lose state, and cause resource churn.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-004-persistent-ssh-sessions.md` (ADR-004: Persistent SSH Sessions)
- IMPLEMENTS → CODE_FILE `mcp/aptl-mcp-common/src/ssh-session.ts` (PersistentSession (split from ssh.ts, issue #790))
- IMPLEMENTS → CODE_FILE `mcp/aptl-mcp-common/src/ssh-manager.ts` (SSHConnectionManager (split from ssh.ts, issue #790))
