---
id: SCN-008
title: "Append-Only Event Timeline"
status: DEPRECATED
type: FUNCTIONAL
priority: SHOULD
wave: 4
created_at: 2026-03-20T06:12:37.730012Z
updated_at: 2026-10-12T18:00:18.618385Z
---

# SCN-008: Append-Only Event Timeline

> Historical requirement record (scope notice added 2026-10-12): The original event logger was removed; its dated trace is retained below. Current run and workflow writers are described in the Experiment Runs reference; this notice does not assert that they implement every event in the original statement.
> The original statement is retained; the rationale records its retirement.
> See the current
> [CLI reference](../../reference/cli.md) and
> [Experiment Runs](../../reference/experiment-runs.md).

## Statement

The system shall maintain an append-only JSONL event log during scenario execution, recording: scenario start/stop, precondition application, objective completion/failure, alert matches, hint requests, and evaluation events. Events shall be flushed immediately for crash safety.

## Rationale

DEPRECATED 2026-10-12: ADR-009 now opens with a historical note: it documents the retired pre-SDL scenario runtime, and its aptl scenario commands and runtime modules are not part of the current branch. c2a8432e removed src/aptl/core/events.py, the JSONL event timeline logger this record traces, on 2026-03-21. OpenTelemetry spans and span events in src/aptl/core/telemetry.py replaced that log. See GitHub issue #954. --- Original rationale: The event timeline provides a chronological record for post-hoc analysis.

## Traceability

- IMPLEMENTS → CODE_FILE `src/aptl/core/events.py` (Event timeline logger, removed by c2a8432e on 2026-03-21)
