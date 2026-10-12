---
id: SCN-008
title: "Append-Only Event Timeline"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 4
created_at: 2026-03-20T06:12:37.730012Z
updated_at: 2026-10-12T18:00:18.618385Z
---

# SCN-008: Append-Only Event Timeline

> Historical requirement record (scope notice added 2026-10-12): The original event logger trace below names a removed file. Current run and workflow writers are described in the Experiment Runs reference; this notice does not assert that they implement every event in the original statement.
> The audited statement and status remain as recorded. See the current
> [CLI reference](../../reference/cli.md) and
> [Experiment Runs](../../reference/experiment-runs.md).

## Statement

The system shall maintain an append-only JSONL event log during scenario execution, recording: scenario start/stop, precondition application, objective completion/failure, alert matches, hint requests, and evaluation events. Events shall be flushed immediately for crash safety.

## Rationale

The event timeline provides a chronological record for post-hoc analysis.

## Traceability

- IMPLEMENTS → CODE_FILE `src/aptl/core/events.py` (Event timeline logger)
