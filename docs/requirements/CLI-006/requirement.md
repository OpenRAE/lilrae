---
id: CLI-006
title: "CLI/Core Separation for Reuse"
status: ACTIVE
type: CONSTRAINT
priority: MUST
wave: 1
created_at: 2026-03-20T06:09:50.020663Z
updated_at: 2026-03-20T06:18:11.648886Z
---

# CLI-006: CLI/Core Separation for Reuse

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/CLI-006/requirement.md).


## Statement

The CLI shall keep a thin command layer separate from the application and domain logic. The application and domain code shall have no dependency on the CLI library or on terminal I/O, so that the web API and direct scripting can reuse it.

## Rationale

The future FastAPI web backend needs to import the same logic without CLI framework dependencies.

## Traceability

- CONSTRAINS → ADR `docs/adrs/adr-007-python-cli-control-plane.md` (ADR-007: Python CLI Control Plane)
