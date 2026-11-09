---
id: SYS-005
title: "Security Operations Center Stack"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-03-20T06:05:35.105398Z
updated_at: 2026-03-20T06:18:11.648321Z
---

# SYS-005: Security Operations Center Stack

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SYS-005/requirement.md).


## Statement

The system shall provide a complete SOC stack supporting the full incident response workflow: alert generation, triage, enrichment, investigation, containment, and reporting.

## Rationale

Wazuh alone provides alerting but lacks threat intelligence context, case management, automated response orchestration, and network-level detection. An agentic SOC where AI agents investigate incidents requires structured workflows, enrichment, and automated response.
