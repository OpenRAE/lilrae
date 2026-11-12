---
id: INF-005
title: "Automated SSL Certificate Generation"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-03-20T06:09:03.791280Z
updated_at: 2026-03-20T06:18:11.648568Z
---

# INF-005: Automated SSL Certificate Generation

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/INF-005/requirement.md).


## Statement

The system shall generate TLS certificates for inter-component encryption (Wazuh Manager, Indexer, Dashboard) at first startup, using a dedicated Docker container for certificate generation.

## Rationale

All Wazuh inter-component communication is TLS-encrypted. Manual certificate management would be error-prone and block first-time users.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-001-docker-compose-deployment.md` (ADR-001: Docker Compose Deployment)
