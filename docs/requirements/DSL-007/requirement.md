---
id: DSL-007
title: "Cleanup and Rollback Definitions in Scenarios"
status: DRAFT
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-03-21T07:52:43.388542Z
updated_at: 2026-10-11T00:00:00.000000Z
---

# DSL-007: Cleanup and Rollback Definitions in Scenarios

## Statement

The APTL backend shall realize RAES-declared cleanup and rollback actions. These actions reverse scenario effects: they remove implants, restore files, and reset credentials. They return a range to a known state without full teardown. The RAES SDL owns how authors declare cleanup. The backend runs the declared actions and fails with explicit diagnostics for unsupported ones.

## Rationale

Without cleanup definitions, environments must be fully rebuilt between runs. Atomic Red Team includes cleanup_command per test. Cleanup definitions enable faster iteration and reduce the dependency on ephemeral environments for every run.

NOT DEPRECATED 2026-10-11: ADR-035 deprecates DSL-002 to DSL-009 as requirements on the retired in-tree DSL. This record stays DRAFT, not DEPRECATED, because its statement now covers how the APTL backend realizes RAES-declared cleanup, not a LilRAE scenario DSL. Open issue #435 still tracks the realization work. On 2026-07-03 the issue moved the cleanup contract to RAES (rae#658) and kept only the backend realization. No other record covers declared cleanup or rollback: the cleanup in RNG-001, DEP-003 and SEC-008 tears down the whole lab. See GitHub issue #435.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#435` (DSL-007: Cleanup and Rollback Definitions in Scenarios)
