---
id: SCN-004
title: "Automated SOC Tool Data Collectors"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-03-20T06:12:24.962267Z
updated_at: 2026-10-31T00:00:00.000000Z
---

# SCN-004: Automated SOC Tool Data Collectors

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SCN-004/requirement.md).


## Statement

The system shall automatically collect data from all SOC tools within the run's time window on scenario stop: Wazuh alerts from the Indexer API, Suricata events, MISP events, and Shuffle workflow executions. Collectors shall be fault-tolerant and use a 120-second HTTP timeout.

## Rationale

Automated collectors ensure complete, consistent data capture for every run.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-009-scenario-engine.md` (ADR-009: Scenario Engine)
- IMPLEMENTS → CODE_FILE `src/aptl/core/collectors.py` (SOC data collectors)
