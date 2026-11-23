---
id: SOC-004
title: "Cortex Enrichment Engine"
status: DEPRECATED
type: FUNCTIONAL
priority: COULD
wave: 2
created_at: 2026-03-20T06:10:46.140823Z
updated_at: 2026-10-31T00:00:00.000000Z
---

# SOC-004: Cortex Enrichment Engine

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SOC-004/requirement.md).


## Statement

The system shall provide Cortex for automated observable enrichment, analyzing IPs, domains, hashes, and emails against external intelligence sources. Cortex shall be integrated with TheHive for case-driven enrichment.

## Rationale

DEPRECATED 2026-10-31: ADR-063 removes Cortex from the TechVault SOC stack together with TheHive, its only consumer. See GitHub issue #1411. --- Original rationale: Cortex automates the enrichment step of the investigation workflow.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-008-soc-stack-integration.md` (ADR-008: SOC Stack Integration)
- DOCUMENTS → ADR `docs/adrs/adr-063-remove-thehive-and-cortex.md` (ADR-063: Remove TheHive and Cortex from the TechVault SOC Stack)
