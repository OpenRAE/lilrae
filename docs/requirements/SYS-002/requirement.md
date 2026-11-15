---
id: SYS-002
title: "Network Segmentation Architecture"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-03-20T06:05:26.135719Z
updated_at: 2026-03-20T06:18:11.648248Z
---

# SYS-002: Network Segmentation Architecture

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SYS-002/requirement.md).


## Statement

The system shall model enterprise network zones using isolated Docker bridge networks with controlled inter-zone communication via multi-homed containers.

## Rationale

A flat network where all containers can reach each other directly does not model real enterprise segmentation. Network zones enable realistic attack paths, zone-based detection, and teachable network security concepts.
