---
id: INF-001
title: "Docker Compose Declarative Deployment"
status: ACTIVE
type: CONSTRAINT
priority: MUST
wave: 1
created_at: 2026-03-20T06:08:50.601173Z
updated_at: 2026-03-20T06:18:11.648478Z
---

# INF-001: Docker Compose Declarative Deployment

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/INF-001/requirement.md).


## Statement

All lab components shall be defined as Docker containers in a single docker-compose.yml file, deployable via docker compose up with no external infrastructure requirements.

## Rationale

Docker Compose provides declarative, reproducible deployment with instant startup and zero cloud costs. Replaces the original AWS/Terraform model that required 30-60 minutes and ~$280/month.

## Traceability

- CONSTRAINS → ADR `docs/adrs/adr-001-docker-compose-deployment.md` (ADR-001: Docker Compose Deployment)
- IMPLEMENTS → CONFIG `docker-compose.yml` (Docker Compose service definitions)
