---
id: SIM-003
title: "Abstract Simulation Model"
status: DRAFT
type: FUNCTIONAL
priority: WONT
wave: 3
created_at: 2026-03-21T07:53:21.665922Z
updated_at: 2026-10-05T07:51:12.874346Z
---

# SIM-003: Abstract Simulation Model

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SIM-003/requirement.md).


## Statement

The platform shall provide an abstract simulation model of the range (network topology, host state, vulnerability surface) that enables what-if analysis, faster-than-real-time execution, and RL agent training without requiring full container emulation.

## Rationale

WITHDRAWN 2026-10-05: An abstract simulation model is a different backend type. RAES (rae#198, RUN-315) and the adapters repository own it. See GitHub issue #486. --- Original rationale: Full emulation is slow (CyGIL training took days for small networks). CyberBattleSim and YAWNING-TITAN demonstrate that abstract simulation enables rapid experimentation. An abstract model complements the emulated range for different use cases.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#486` (SIM-003: Abstract Simulation Model)
