---
id: INF-010
title: "Declarative Range Definition"
status: DRAFT
type: FUNCTIONAL
priority: WONT
wave: 6
created_at: 2026-03-21T03:56:18.575009Z
updated_at: 2026-10-09T00:00:00.000000Z
---

# INF-010: Declarative Range Definition

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/INF-010/requirement.md).


## Statement

The system shall provide a single declarative range definition that describes the containers in a lab topology, including their names, network addresses, exposed services, SSH access parameters, and roles. All components that need to know about containers (orchestration, terminal access, snapshots, UI, health checks) shall derive their behavior from this definition rather than maintaining independent hardcoded maps.

## Rationale

WITHDRAWN 2026-10-09: The RAES SDL already provides declarative range definition, and realizing declared ranges is already the backend's core work. The issue closed as satisfied upstream on 2026-07-03. See GitHub issue #500. --- Original rationale: Container SSH parameters, port mappings, and service endpoints are currently duplicated across terminal.py, snapshot.py, lab.py, and ContainerCard.svelte. Adding a new scenario or container requires updating every copy in lockstep. A single range definition eliminates this duplication and makes the system extensible to arbitrary lab topologies.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#500` (INF-010: Declarative Range Definition)
