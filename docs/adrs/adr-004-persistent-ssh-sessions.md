# ADR-004: Persistent SSH Session Architecture with Command Queuing

## Status

accepted

## Date

2025-08-30

## Context

Agents send container commands through MCP tools.
A separate SSH connection for every command adds connection overhead and loses shell state.
The command transport therefore needs an explicit owner for long-lived SSH sessions.
MCP tool requests alone do not provide that shell-state contract.
This is not a claim that MCP has no protocol-level session support.

### Problems with Per-Command SSH

The original observations estimated 200–500 ms for handshake, authentication, and channel setup per command.
Those timings describe early tests, not a current performance guarantee.
A new shell loses the previous shell's environment, current directory, aliases, and history.
Closing its connection can also affect associated background work.
Repeated connections consume daemon work and file descriptors.

### AI Agent Behavior Patterns

Early tests observed sequences of 5–20 reconnaissance commands.
Agents used `export`, `cd`, and `alias`, and expected later commands to use that state.
They mixed long scans or compilation with short observations.
Some abandoned a session when they changed approach.
These observations explain persistent sessions, independent sessions, and bounded cleanup.

## Decision

Use the common `PersistentSession` and `SSHConnectionManager` owners for persistent shells and queued commands.
`mcp/aptl-mcp-common/src/ssh.ts` remains the public export boundary.
The current implementation separates `ssh-session.ts`, `ssh-manager.ts`, and `ssh-contracts.ts` behind that boundary.
Python `src/aptl/core/ssh.py` owns keys and public-key distribution, not this runtime session protocol.

### Architecture

```text
Agent -> MCP tool dispatch -> SSHConnectionManager -> PersistentSession
                                                   -> SSH channel -> container shell
                                  |
                                  -> session pool: separate interactive and background sessions
```

### Key Design Elements

A session keeps one shell channel and preserves its state across commands.
The default inactivity timeout is 10 minutes and is configurable.
A command has a separate default timeout of 30 seconds and can select a longer bound.
The session timeout and command timeout have different meanings.

Normal-mode commands use unique start and end delimiters.
The formatter includes the command identity and an exit-code marker.
The parser finds the command's bounded output and exit code in the shared stream.
The conceptual original example was:

```bash
echo '<<<DELIM_abc123_START>>>'
<actual command>
echo '<<<DELIM_abc123_END_$?>>>'
```

This is historical pseudocode, not the current executable envelope or a shell procedure.
`ShellFormatter` supplies shell-specific syntax for bash, sh, PowerShell, and cmd.
The current parser combines received shell output into `stdout` and leaves `stderr` empty for that result.
It does not reconstruct independent streams from a shared PTY.

The FIFO queue runs one command at a time within a session.
A slow command therefore delays later commands in that session.
An independent session provides a separate queue.
A background submission returns after queuing; that return does not prove command completion.
Background commands still use their session's queue.

The original description called the buffer bounds 10,000 and 5,000 lines.
The current implementation bounds an array of received output chunks at 10,000 entries and trims it to 5,000.
A chunk is not necessarily one line.
The output result reports dropped chunks rather than silently claiming a complete buffer.
The bound avoids unlimited accumulation but can discard early output.

SSH keepalive uses a 30-second interval and a maximum of three missed responses.
Session metadata returns copies of mutable containers so callers cannot directly change internal history or environment maps.
Shell formatters preserve the shared transport interface across shell types.
Their presence does not qualify a complete Windows endpoint deployment.

### Connection Manager

The manager owns session creation, lookup, listing, and removal.
It uses SSH key authentication and coordinates connection lifecycle.
Its close paths reject pending command promises and close owned sessions.
The v4.6.7 fix addressed callers left waiting during cleanup.
The later amendments below define the required failure and close semantics.

## Consequences

### Positive

- A sequence of commands can share shell state.
- One connection avoids a handshake for each command.
- Separate sessions support separate tasks on one target.
- Shell-specific formatters reuse the common session owner.

The original record expected an order-of-magnitude latency improvement.
That expectation is not a current benchmark or a guarantee for remote commands.

### Negative

- Delimiter parsing can fail if output resembles an envelope; unique identities reduce accidental collisions.
- Persistent connections and shell processes need timeouts and explicit cleanup.
- One long command blocks later commands in the same session.

### Risks

A short inactivity timeout can interrupt work; a long timeout can waste resources.
The 10-minute choice reflected early interaction observations.
Buffer trimming can lose useful early output.
The v4.6.7 cleanup defect showed why every close path needs pending-command checks.
The current [MCP reference](../reference/mcp.md) supplies supported tool contracts.

## Update (2026-05-12): Contract hardening guardrails

Issue #215 defines session use and cleanup contracts at the common SSH owner.
`PersistentSession.executeCommand()`, `close()/cleanup()`, and the manager's execution and close methods are the affected boundary.
A parallel Python session manager or key-generation test cannot satisfy this contract.

Accepted commands require an initialized session, an open shell, and active manager ownership.
Every close, timeout, shell-close, manager-removal, and shutdown path must leave the session inactive.
Cleanup must clear keepalive, session, and command timers.
It must reject in-flight and queued commands exactly once.

Failures use the existing `SSHError` and MCP result paths.
`traceToolCall()` and redaction must remain safe.
The change must not add another exception hierarchy, result envelope, or raw-secret log path.
JSON Schema tool definitions and `LabConfig`/`getTargetCredentials` remain the input and configuration boundaries.
A local copy of those schemas is not a replacement.

Common-library changes require affected SSH tests and dependent MCP rebuilds in CI.
A future Python runtime SSH owner would need a separate architectural decision.
The current Python key owner does not acquire that responsibility through this amendment.

## Update (2026-05-18): Effective session-mode metadata

An omitted `raw` argument uses the session default.
It does not select normal mode automatically.
Effective command mode is therefore a runtime fact.

`session_command` results must expose `session_mode: "raw" | "normal"` through the existing `SessionMode` vocabulary.
Session metadata `mode` keeps its creation-time meaning.
It does not prove the mode of a command with an override.
The existing result envelope, `SSHError`, JSON Schema, and `assertSessionIdContract` boundary remain authoritative.
No parallel session model or ad hoc validator replaces them.

Raw-mode `code: 0` is an unknown-outcome transport artifact.
Observability must use effective mode rather than infer success from that code.

## Update (2026-05-18): Awaitable remote-close boundary

Issue #304 distinguishes local cleanup from observed remote shell closure.
`close()` resolves after the SSH channel's remote `close` event or a visible bounded timeout.
Local cleanup and `shell.end()` alone do not prove remote cessation.

`closed` requires verified cleanup and either observed remote close or the visible timeout path.
`error` remains the broken-session path.
The existing `SSHError` and MCP envelope remain in use.
There is no new close result type or handler-specific failure shape.

Cleanup rejects waiting commands before the remote-close wait finishes.
Capture harvest stays in `captures.ts`, and tool orchestration stays in `handlers.ts`.
The SSH layer owns channel lifecycle.
The internal close-timeout constant is the extension point; no new tool argument or configuration key is required.
