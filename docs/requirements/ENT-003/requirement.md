---
id: ENT-003
title: "PostgreSQL Database with Sensitive Data"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 3
created_at: 2026-03-20T06:11:09.322834Z
updated_at: 2026-03-20T06:18:11.649332Z
---

# ENT-003: PostgreSQL Database with Sensitive Data

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/ENT-003/requirement.md).


## Statement

The system shall provide a PostgreSQL 16 database on the internal network (172.20.2.11) containing a techvault database with customers table (PII) and backup_config table (AWS access keys). pg_hba.conf shall trust the entire internal subnet.

## Rationale

The database is the high-value target containing data worth exfiltrating.
