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

## Statement

The CLI shall keep a thin command layer separate from the application and domain logic. The application and domain code shall have no dependency on the CLI library or on terminal I/O, so that the web API and direct scripting can reuse it.

## Rationale

The future FastAPI web backend needs to import the same logic without CLI framework dependencies.

## Traceability

- CONSTRAINS → ADR `docs/adrs/adr-007-python-cli-control-plane.md` (ADR-007: Python CLI Control Plane)
