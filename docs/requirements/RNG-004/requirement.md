---
id: RNG-004
title: "Multi-Domain AD Forest Topologies"
status: DRAFT
type: FUNCTIONAL
priority: WONT
wave: 4
created_at: 2026-03-21T07:50:20.970774Z
updated_at: 2026-03-21T07:50:20.970774Z
---

# RNG-004: Multi-Domain AD Forest Topologies

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/RNG-004/requirement.md).


## Statement

The lab shall support multi-domain Active Directory forest topologies with trust relationships, enabling scenarios that exercise cross-domain attacks (golden ticket, trust abuse, SID history injection) found in real enterprise environments.

## Rationale

ENT-002 provides a single domain (TECHVAULT.LOCAL). Real enterprises use forests with multiple domains and trusts. Cross-domain attacks are a significant portion of modern threat activity.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#497` (RNG-004: Multi-Domain AD Forest Topologies)
