---
id: SOC-005
title: "Shuffle SOAR with Pre-Built Playbooks"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-03-20T06:10:49.871180Z
updated_at: 2026-10-31T00:00:00.000000Z
---

# SOC-005: Shuffle SOAR with Pre-Built Playbooks

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SOC-005/requirement.md).


## Statement

The system shall provide Shuffle SOAR with a pre-built playbook for IOC enrichment (Wazuh alert to a MISP lookup of the alert's source IP). Shuffle shall accept webhook triggers from Wazuh for alerts level 10+.

## Rationale

Shuffle's security-specific integrations enable automated investigation workflows.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-008-soc-stack-integration.md` (ADR-008: SOC Stack Integration)
