---
id: SIEM-003
title: "OpenSearch-Based Alert Storage and Query"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-03-20T06:10:23.648268Z
updated_at: 2026-03-20T06:18:11.649058Z
---

# SIEM-003: OpenSearch-Based Alert Storage and Query

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SIEM-003/requirement.md).


## Statement

The system shall provide a Wazuh Indexer (OpenSearch) on port 9200 for storing and querying alerts, archives, and FIM data. The indexer shall be accessible for direct queries by MCP servers and data collectors.

## Rationale

OpenSearch provides the rich query language needed for MCP-based AI agent investigation.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-002-wazuh-siem.md` (ADR-002: Wazuh SIEM)
