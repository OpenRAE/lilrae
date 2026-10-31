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

## Statement

The system shall provide Shuffle SOAR with a pre-built playbook for IOC enrichment (Wazuh alert to a MISP lookup of the alert's source IP). Shuffle shall accept webhook triggers from Wazuh for alerts level 10+.

## Rationale

Shuffle's security-specific integrations enable automated investigation workflows.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-008-soc-stack-integration.md` (ADR-008: SOC Stack Integration)
