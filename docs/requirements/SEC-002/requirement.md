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

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SEC-002/requirement.md).


## Statement

The CLI and core modules shall maintain an automated test suite covering all core modules (lab, config, env, ssh, certs, credentials, services, scenarios, session, events, collectors, runstore, exporter, snapshot, health, flags, detection). Tests shall replace Docker and process execution with test doubles.

## Rationale

587+ tests provide confidence in orchestration logic, credential handling, and data collection.
