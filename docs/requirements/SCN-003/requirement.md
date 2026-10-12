---
id: SCN-003
title: "Run Lifecycle Management"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-03-20T06:12:21.335980Z
updated_at: 2026-10-12T18:00:18.618385Z
---

# SCN-003: Run Lifecycle Management

> Historical requirement record (scope notice added 2026-10-12): The statement describes the retired scenario runtime and archive assembler. The shipped lifecycle uses `aptl lab start` and `aptl lab stop`; run records are described in the current Experiment Runs reference.
> The audited statement and status remain as recorded. See the current
> [CLI reference](../../reference/cli.md) and
> [Experiment Runs](../../reference/experiment-runs.md).

## Statement

The scenario engine shall manage run lifecycle: aptl scenario start validates prerequisites, records start timestamp, and creates a run directory; aptl scenario stop records end timestamp, executes data collectors, captures range snapshot, and assembles the run archive.

## Rationale

Precise start/end timestamps define the time window for data collection.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-009-scenario-engine.md` (ADR-009: Scenario Engine)
