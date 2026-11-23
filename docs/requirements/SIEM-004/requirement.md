---
id: SIEM-004
title: "Web-Based SIEM Dashboard"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-03-20T06:10:26.342040Z
updated_at: 2026-03-20T06:18:11.649080Z
---

# SIEM-004: Web-Based SIEM Dashboard

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SIEM-004/requirement.md).


## Statement

The system shall provide a Wazuh Dashboard (OpenSearch Dashboards) on port 443 for visual alert investigation, log exploration, and security event analysis.

## Rationale

A web dashboard provides the visual investigation interface that security analysts expect.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-002-wazuh-siem.md` (ADR-002: Wazuh SIEM)
