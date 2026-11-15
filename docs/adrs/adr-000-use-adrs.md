# ADR-000: Use Architecture Decision Records

## Status

accepted

## Date

2026-03-20

## Context

APTL developed through four major versions.
Version 1.x used AWS and Terraform.
Version 2.0 introduced Docker Compose.
Version 3.x added TypeScript MCP servers and a common library.
Version 4.x added enterprise services, the Python CLI, the SOC stack, and the scenario engine.

Earlier decisions appeared in commit messages, CHANGELOG entries, and `notes/team-review-synthesis.md`.
Contributors needed a stable place to find each decision and its reasons.
Without that record, later work could lose the original context and repeat the same discussion.

## Decision

The project uses Architecture Decision Records in its existing MADR format.
ADRs live in `docs/adrs/` and share version control with the code.
Each record states its status, date, context, decision, and consequences.
Consequences include benefits, costs, and risks.
The [format reference](../reference/architecture-decisions.md) contains the template.

### Governance

An accepted decision is immutable.
A new decision supersedes it when its meaning changes.
An editorial rewrite preserves that meaning and keeps amendments and successor links explicit.

ADR numbers are sequential and never reused.
The records live with the code, not in a separate wiki.
A proposed ADR can become accepted or rejected.
An accepted ADR can later become deprecated or superseded by another ADR.
The index changes when a record is added or its recorded status changes.

## Consequences

### Positive

- Contributors can find design reasons without reconstructing every commit.
- The documentation site makes decisions searchable.
- Decision immutability prevents silent changes of meaning.
- Retrospective records preserve earlier design knowledge.

### Negative

- Significant decisions need a written record and index maintenance.
- A retrospective record can miss parts of the original reasoning.

### Risks

- An index can become stale when a successor decision changes applicability.
- Contributors can disagree about which decisions need an ADR.
