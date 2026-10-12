---
id: CLI-005
title: "Scenario Start/Stop/List Commands"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-03-20T06:09:44.776757Z
updated_at: 2026-10-12T18:00:18.618385Z
---

# CLI-005: Scenario Start/Stop/List Commands

> Historical requirement record (scope notice added 2026-10-12): The statement names the retired scenario command group. Current lifecycle commands are `aptl lab scenarios`, `aptl lab start --scenario` and `aptl lab stop`.
> The audited statement and status remain as recorded. See the current
> [CLI reference](../../reference/cli.md) and
> [Experiment Runs](../../reference/experiment-runs.md).

## Statement

The CLI shall provide aptl scenario start, aptl scenario stop, and aptl scenario list commands for scenario lifecycle management.

## Rationale

Scenario execution is the primary research workflow. The lifecycle traces
now point to the shipped lab commands; the historical notice dates the
retirement of the command names in the statement. See GitHub issue #954.

## Traceability

- IMPLEMENTS → CODE_FILE `src/aptl/cli/lab.py` (aptl lab scenarios, aptl lab start --scenario and aptl lab stop)
- TESTS → TEST `tests/test_cli.py` (TestLabStartCommand, TestLabStopCommand and the aptl lab scenarios tests)
