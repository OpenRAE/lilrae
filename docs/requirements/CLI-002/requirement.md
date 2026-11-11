---
id: CLI-002
title: "Pydantic Configuration Validation"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-03-20T06:09:36.363308Z
updated_at: 2026-03-20T06:18:11.648800Z
---

# CLI-002: Pydantic Configuration Validation

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/CLI-002/requirement.md).


## Statement

The CLI shall validate aptl.json configuration using Pydantic models before any deployment operation. Validation shall catch invalid JSON, missing fields, type errors, and impossible profile combinations.

## Rationale

The bash script passed invalid configurations silently, causing containers to fail with cryptic errors.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-007-python-cli-control-plane.md` (ADR-007: Python CLI Control Plane)
- IMPLEMENTS → CODE_FILE `src/aptl/core/config.py` (Pydantic configuration models)
- TESTS → TEST `tests/test_config.py` (Pydantic config model validation tests)
- TESTS → TEST `tests/test_scenario_source_config.py` (Strict scenario and release-source configuration)
- IMPLEMENTS → CODE_FILE `src/aptl/cli/config.py` (aptl config validate command)
- IMPLEMENTS → CODE_FILE `src/aptl/cli/_common.py` (resolve_config_for_cli helper)
- TESTS → TEST `tests/test_cli_config.py` (CLI config validate/show tests)
- IMPLEMENTS → GITHUB_ISSUE `138` (Issue 138: implement stubbed CLI commands)
- IMPLEMENTS → ADR `docs/adrs/adr-025-strict-first-party-config-schema.md` (ADR-025: Strict first-party config schema)
