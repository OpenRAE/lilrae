---
id: SEC-005
title: ".env Credential Isolation from Version Control"
status: ACTIVE
type: CONSTRAINT
priority: MUST
wave: 1
created_at: 2026-03-20T06:10:12.887986Z
updated_at: 2026-03-20T06:18:11.648994Z
---

# SEC-005: .env Credential Isolation from Version Control

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SEC-005/requirement.md).


## Statement

Runtime credentials shall be stored exclusively in a .env file that is listed in .gitignore. docker-compose.yml shall reference credentials only through variable substitution. No credentials shall be committed to version control.

## Rationale

Credential leakage to version control is a common and severe security mistake.

## Traceability

- IMPLEMENTS → CODE_FILE `src/aptl/utils/placeholders.py` (.env.example placeholder marker registry)
- IMPLEMENTS → CODE_FILE `src/aptl/core/env.py` (.env loader + sensitive-var placeholder guard)
- IMPLEMENTS → CODE_FILE `src/aptl/core/lab.py` (Lab-start placeholder-secret guard)
- TESTS → TEST `tests/test_env.py` (Placeholder-guard tests)
