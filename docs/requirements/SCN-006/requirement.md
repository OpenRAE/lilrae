---
id: SCN-006
title: "Run Archive Packaging and S3 Export"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 4
created_at: 2026-03-20T06:12:31.195451Z
updated_at: 2026-03-20T06:18:11.649805Z
---

# SCN-006: Run Archive Packaging and S3 Export

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SCN-006/requirement.md).


## Statement

The system shall support exporting completed runs as tar.gz archives with SHA-256 checksums, with optional S3 upload. Run storage backend shall be configurable via aptl.json.

## Rationale

Run archives enable sharing, long-term storage, and offline analysis.

## Traceability

- IMPLEMENTS → CODE_FILE `src/aptl/core/exporter.py` (Run archive exporter)
- IMPLEMENTS → ADR `docs/adrs/adr-009-scenario-engine.md` (ADR-009: Scenario Engine)
