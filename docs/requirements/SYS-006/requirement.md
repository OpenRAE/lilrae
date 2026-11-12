---
id: SYS-006
title: "CLI Control Plane"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-03-20T06:05:37.300399Z
updated_at: 2026-03-20T06:18:11.648386Z
---

# SYS-006: CLI Control Plane

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SYS-006/requirement.md).


## Statement

The system shall provide a CLI (lilrae) as the primary control plane for lab lifecycle management, configuration, scenario execution, and container operations.

## Rationale

The original bash script (start-lab.sh) lacked error handling, state management, configuration validation, and only supported 4 of 9 profiles. A Python CLI provides structured error handling, Pydantic validation, extensibility, and a testable core domain layer shared with the future web UI.
