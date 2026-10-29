---
id: OBS-003
title: "Agent Reasoning Traces"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-03-21T07:50:38.812913Z
updated_at: 2026-10-12T18:00:18.618385Z
---

# OBS-003: Agent Reasoning Traces

## Statement

The platform shall capture agent reasoning traces that record why decisions were made (goals considered, alternatives evaluated, planning rationale), not just what actions were executed.

## Rationale

Current tracing records tool invocations but not the reasoning behind them. Understanding agent decision-making is essential for debugging, improving, and trusting autonomous agent behavior.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `228` (OBS-003: Agent Reasoning Traces)
- TESTS → TEST `tests/test_consistency.py` (TestKaliContainerLifecycle: realized Kali systemd, native SSH and internal-network contracts)
- DOCUMENTS → GITHUB_ISSUE `304` (Await remote SSH channel close in PersistentSession.close before harvest)
- DOCUMENTS → GITHUB_ISSUE `305` (Privileged capture writer: take Kali captures out of the kali user's reach)
- TESTS → TEST `mcp/aptl-mcp-common/tests/runs.test.ts` (Per-run dir helpers + createPtyTeeWriter + writer.flush drain)
- IMPLEMENTS → ADR `docs/adrs/adr-033-agent-reasoning-trace-boundary.md` (ADR-033: Red-Side Behavioural Capture and Non-Contamination Boundary)
- IMPLEMENTS → ADR `docs/adrs/adr-027-red-team-structured-logging.md` (ADR-027 (amended): Red Team Structured Logging Boundary: SIEM transport superseded by ADR-033)
- IMPLEMENTS → CODE_FILE `src/aptl/core/runstore.py` (Session-scoped subdirectory helpers + resolve_active_run_dir)
- IMPLEMENTS → CODE_FILE `src/aptl/core/session.py` (Writes/clears trace-context.json on scenario lifecycle)
- IMPLEMENTS → CODE_FILE `src/aptl/utils/redaction.py` (Scoped APTL_EXPERIMENT_NO_REDACT accessor + impacket -hashes redaction)
- IMPLEMENTS → CODE_FILE `mcp/aptl-mcp-common/src/runs.ts` (Per-run directory contract + createPtyTeeWriter + PtyTeeWriter.flush)
- IMPLEMENTS → CODE_FILE `mcp/aptl-mcp-common/src/captures.ts` (harvestSession copies per-session broker output or records a bounded harvest failure)
- IMPLEMENTS → CODE_FILE `mcp/aptl-mcp-common/src/redaction.ts` (Scoped experimentNoRedactActive accessor + impacket -hashes patterns)
- IMPLEMENTS → CODE_FILE `mcp/aptl-mcp-common/src/tools/definitions.ts` (Canonical SESSION_ID_SCHEMA applied to every session_id tool argument)
- IMPLEMENTS → CODE_FILE `mcp/aptl-mcp-common/src/tools/handlers.ts` (assertSessionIdContract + maybeHarvest wiring (close_session / close_all_sessions harvest_warning))
- IMPLEMENTS → CODE_FILE `mcp/mcp-red/src/capture.ts` (Per-run tool-call JSONL routing + experimentalRedact wrapper)
- IMPLEMENTS → CODE_FILE `mcp/mcp-red/src/logger.ts` (localOcsfJsonlSink + defaultRedTeamSinks (SIEM dispatch removed))
- IMPLEMENTS → CODE_FILE `mcp/mcp-red/src/index.ts` (extractSessionId propagates exec sessionId from result envelope)
- IMPLEMENTS → CONFIG `containers/kali/audit/aptl.rules` (APTL auditd ruleset (execve + connect + file ops on /home/kali /tmp /root /etc))
- IMPLEMENTS → CONFIG `docker-compose.capture.yml` (Backend-owned capture volume and SSH sidecar with only required daemon capabilities)
- TESTS → TEST `tests/test_redaction.py` (TestExperimentNoRedactToggle scoped-accessor invariant)
- TESTS → TEST `tests/test_runstore.py` (TestSessionScopedHelpers + TestResolveActiveRunDir)
- TESTS → TEST `tests/test_session.py` (trace-context.json write/clear on scenario lifecycle)
- TESTS → TEST `mcp/aptl-mcp-common/tests/captures.test.ts` (harvestSession happy/missing-source/globals/permissions/runId-opt + docker bin resolution)
- TESTS → TEST `mcp/aptl-mcp-common/tests/ssh.test.ts` (SendEnv APTL_* + PTY tee + boundRunId + getShellType assertions)
- TESTS → TEST `mcp/aptl-mcp-common/tests/redaction.test.ts` (Scoped experimentNoRedactActive invariant + impacket -hashes negative assertion)
- TESTS → TEST `mcp/aptl-mcp-common/tests/tools-handlers.test.ts` (assertSessionIdContract rejection across handlers + close_session/close_all_sessions envelope)
- TESTS → TEST `mcp/mcp-red/tests/capture.test.ts` (Per-run tool-call JSONL routing + result-content content-equality + experimentalRedact)
- TESTS → TEST `mcp/mcp-red/tests/logger.test.ts` (localOcsfJsonlSink + defaultRedTeamSinks + sink-error return-value contract)
- TESTS → TEST `tests/test_kali_capture_compose.py` (Compose-consistency tests for the ADR-041 boundary: no kali mount, sidecar caps/namespaces/ports)
- IMPLEMENTS → CODE_FILE `mcp/aptl-mcp-common/src/ssh-session.ts` (Continuous PTY tee + SendEnv APTL_* + boundRunId in PersistentSession (split from ssh.ts, issue #790))
- IMPLEMENTS → CODE_FILE `containers/kali-capture/broker.py` (Kali session transcript broker: the capture sidecar's ForceCommand, which refuses a session without the active run's custody environment and records frames.jsonl per session)
- IMPLEMENTS → CODE_FILE `src/aptl/core/deployment/_compose_capture_apparatus.py` (Admits the kali-capture sidecar and moves the Kali sshd to 127.0.0.1:2222 behind it)
