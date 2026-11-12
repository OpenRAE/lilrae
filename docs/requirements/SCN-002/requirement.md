---
id: SCN-002
title: "MITRE ATT&CK Technique Mapping"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-03-20T06:12:17.729530Z
updated_at: 2026-03-20T06:18:11.649715Z
---

# SCN-002: MITRE ATT&CK Technique Mapping

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SCN-002/requirement.md).


## Statement

Every scenario shall declare the MITRE ATT&CK tactics and techniques it exercises, both at the scenario level and at each step. This shall enable ATT&CK coverage analysis across scenarios.

## Rationale

MITRE ATT&CK is the standard framework for describing adversary behavior.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-009-scenario-engine.md` (ADR-009: Scenario Engine)
