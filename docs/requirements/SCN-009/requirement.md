---
id: SCN-009
title: "Scenario Prerequisite Validation"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-03-20T06:12:40.178955Z
updated_at: 2026-10-12T18:00:18.618385Z
---

# SCN-009: Scenario Prerequisite Validation

> Historical requirement record (scope notice added 2026-10-12): The statement names the retired scenario command group. The shipped `aptl lab start --scenario` path validates the admitted scenario and its prerequisite contracts.
> The audited statement and status remain as recorded. See the current
> [CLI reference](../../reference/cli.md) and
> [Experiment Runs](../../reference/experiment-runs.md).

## Statement

aptl scenario start shall validate that all required lab profiles (as declared in the scenario YAML) are enabled in aptl.json and their containers are running, before starting a session.

## Rationale

Prerequisite validation catches configuration mismatches before the scenario begins.
