---
id: SCN-003
title: "Run Lifecycle Management"
status: DEPRECATED
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-03-20T06:12:21.335980Z
updated_at: 2026-10-12T17:30:00.000000Z
---

# SCN-003: Run Lifecycle Management

## Statement

The scenario engine shall manage run lifecycle: aptl scenario start validates prerequisites, records start timestamp, and creates a run directory; aptl scenario stop records end timestamp, executes data collectors, captures range snapshot, and assembles the run archive.

## Rationale

DEPRECATED 2026-10-12: ADR-009 now opens with a historical note: it documents the retired pre-SDL scenario runtime, and its aptl scenario commands and runtime modules are not part of the current branch. ba1e5491 removed the aptl scenario start and aptl scenario stop commands this statement names on 2026-03-29. aptl lab start and aptl lab stop now start and stop the lab (CLI-005), and docs/reference/experiment-runs.md describes the run record, range snapshot and provenance they write. See GitHub issue #954. --- Original rationale: Precise start/end timestamps define the time window for data collection.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-009-scenario-engine.md` (ADR-009: Scenario Engine)
