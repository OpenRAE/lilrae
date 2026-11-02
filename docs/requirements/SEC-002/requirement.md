---
id: SEC-002
title: "Control-Plane Test Suite"
status: ACTIVE
type: NON_FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-03-20T06:10:06.719135Z
updated_at: 2026-03-20T06:18:11.648929Z
---

# SEC-002: Control-Plane Test Suite

## Statement

The CLI and core modules shall maintain an automated test suite covering all core modules (lab, config, env, ssh, certs, credentials, services, scenarios, session, events, collectors, runstore, exporter, snapshot, health, flags, detection). Tests shall replace Docker and process execution with test doubles.

## Rationale

587+ tests provide confidence in orchestration logic, credential handling, and data collection.
