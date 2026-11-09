---
id: RNG-003
title: "Snapshot/Restore for Mid-Scenario Checkpointing"
status: DRAFT
type: FUNCTIONAL
priority: WONT
wave: 2
created_at: 2026-03-21T07:50:17.358990Z
updated_at: 2026-10-05T07:51:12.874346Z
---

# RNG-003: Snapshot/Restore for Mid-Scenario Checkpointing

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/RNG-003/requirement.md).


## Statement

The platform shall support snapshotting the complete range state (container filesystems, volumes, network state) at arbitrary points during scenario execution, and restoring from those snapshots for replay, branching, or recovery.

## Rationale

WITHDRAWN 2026-10-05: Compose cannot give complete-state checkpoints at arbitrary points with deterministic replay (preflight on 2026-07-17). A scenario that needs cold checkpoints gets a new, narrow requirement. See GitHub issue #453. --- Original rationale: SCN-005 captures range snapshots but only for metadata (versions, rules inventory). Full state snapshot/restore enables what-if analysis, checkpoint/restart for long exercises, and deterministic replay.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#453` (RNG-003: Snapshot/Restore for Mid-Scenario Checkpointing)
