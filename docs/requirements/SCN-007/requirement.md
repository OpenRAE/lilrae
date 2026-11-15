---
id: SCN-007
title: "Objective-Based Scoring with Hints"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 4
created_at: 2026-03-20T06:12:34.196096Z
updated_at: 2026-03-20T06:18:11.649825Z
---

# SCN-007: Objective-Based Scoring with Hints

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SCN-007/requirement.md).


## Statement

Scenarios shall define red and blue objectives with point values. Red objectives shall be scored via Wazuh alert matching or command output verification. Hints shall provide progressive disclosure with point penalties.

## Rationale

Objective scoring provides a quantitative measure of agent/operator performance.

## Traceability

- IMPLEMENTS → CODE_FILE `src/aptl/core/flags.py` (Objective scoring engine)
