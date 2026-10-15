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

> Historical command note (updated 2026-10-12): the rationale records the
> removed command names and source files. The statement and traces describe
> the current lab lifecycle.

## Statement

The CLI shall provide aptl lab scenarios, aptl lab start --scenario, and aptl lab stop commands for scenario lifecycle management.

## Rationale

UPDATED 2026-10-12: The statement named aptl scenario start, aptl scenario stop and aptl scenario list. ba1e5491 removed those commands on 2026-03-29, with src/aptl/cli/scenario.py and tests/test_cli_scenario.py. The statement and the traces now name aptl lab scenarios, aptl lab start --scenario and aptl lab stop, which provide that lifecycle. See GitHub issue #954. --- Original rationale: Scenario execution is the primary research workflow.

## Traceability

- IMPLEMENTS → CODE_FILE `src/aptl/cli/lab.py` (aptl lab scenarios, aptl lab start --scenario and aptl lab stop)
- TESTS → TEST `tests/test_cli.py` (TestLabStartCommand, TestLabStopCommand and the aptl lab scenarios tests)
