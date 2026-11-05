---
id: SOC-003
title: "TheHive Case Management"
status: DEPRECATED
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-03-20T06:10:43.754595Z
updated_at: 2026-10-31T00:00:00.000000Z
---

# SOC-003: TheHive Case Management

## Statement

The system shall provide TheHive 5 for incident case management, supporting case creation from Wazuh alerts, observable tracking, timeline documentation, and investigation workflow via REST API.

## Rationale

DEPRECATED 2026-10-31: ADR-063 removes TheHive from the TechVault SOC stack. TheHive 5 needs a license for each instance after a 14-day trial, and its Community terms prohibit distribution. The lab has no case-management tool. See GitHub issue #1411. --- Original rationale: Case management provides the structured workflow AI agents need to conduct investigations.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-008-soc-stack-integration.md` (ADR-008: SOC Stack Integration)
- DOCUMENTS → ADR `docs/adrs/adr-063-remove-thehive-and-cortex.md` (ADR-063: Remove TheHive and Cortex from the TechVault SOC Stack)
