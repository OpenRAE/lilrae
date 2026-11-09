---
id: SYS-001
title: "Platform Deployment and Lifecycle"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-03-20T06:05:22.525771Z
updated_at: 2026-03-20T06:18:11.648196Z
---

# SYS-001: Platform Deployment and Lifecycle

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SYS-001/requirement.md).


## Statement

The system shall provide a self-contained, locally deployable purple team lab environment that starts, stops, and manages its lifecycle without external cloud dependencies.

## Rationale

Eliminates cloud cost barriers ($280/month AWS) and multi-hour deployment times. Enables offline operation and single-command startup for security practitioners.
