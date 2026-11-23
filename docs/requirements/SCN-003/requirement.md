---
id: SCN-003
title: "Run Lifecycle Management"
status: DEPRECATED
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-03-20T06:12:21.335980Z
updated_at: 2026-10-12T18:00:18.618385Z
---

# SCN-003: Run Lifecycle Management

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SCN-003/requirement.md).


> Historical requirement record (scope notice added 2026-10-12): The statement describes the retired scenario runtime and archive assembler. The shipped lifecycle uses `aptl lab start` and `aptl lab stop`; run records are described in the current Experiment Runs reference.
> The original statement is retained; the rationale records its retirement.
> See the current
> [CLI reference](../../reference/cli.md) and
> [Experiment Runs](../../reference/experiment-runs.md).

## Statement

The scenario engine shall manage run lifecycle: aptl scenario start validates prerequisites, records start timestamp, and creates a run directory; aptl scenario stop records end timestamp, executes data collectors, captures range snapshot, and assembles the run archive.

## Rationale

DEPRECATED 2026-10-12: ADR-009 now opens with a historical note: it documents the retired pre-SDL scenario runtime, and its aptl scenario commands and runtime modules are not part of the current branch. ba1e5491 removed the aptl scenario start and aptl scenario stop commands this statement names on 2026-03-29. aptl lab start and aptl lab stop now start and stop the lab (CLI-005), and docs/reference/experiment-runs.md describes the run record, range snapshot and provenance they write. See GitHub issue #954. --- Original rationale: Precise start/end timestamps define the time window for data collection.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-009-scenario-engine.md` (ADR-009: Scenario Engine)
