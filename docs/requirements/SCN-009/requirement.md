---
id: SCN-009
title: "Scenario Prerequisite Validation"
status: DEPRECATED
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-03-20T06:12:40.178955Z
updated_at: 2026-10-12T17:30:00.000000Z
---

# SCN-009: Scenario Prerequisite Validation

## Statement

aptl scenario start shall validate that all required lab profiles (as declared in the scenario YAML) are enabled in aptl.json and their containers are running, before starting a session.

## Rationale

DEPRECATED 2026-10-12: ADR-009 now opens with a historical note: it documents the retired pre-SDL scenario runtime, and its aptl scenario commands and runtime modules are not part of the current branch. ba1e5491 removed the aptl scenario start command this statement names on 2026-03-29, together with the scenario YAML and the session it describes. An RAES SDL scenario now selects its Compose profiles when aptl lab start admits it. See GitHub issue #954. --- Original rationale: Prerequisite validation catches configuration mismatches before the scenario begins.
