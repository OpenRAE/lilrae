---
id: REP-004
title: "Traffic Generation Profiles"
status: DRAFT
type: FUNCTIONAL
priority: COULD
wave: 3
created_at: 2026-03-21T07:53:00.981772Z
updated_at: 2026-10-05T07:51:12.874346Z
---

# REP-004: Traffic Generation Profiles

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/REP-004/requirement.md).


## Statement

The platform shall support declarative traffic generation profiles that specify baseline and background network traffic patterns (web browsing, email, DNS, authentication) for realistic experiment conditions, using either replay or synthetic generation.

## Rationale

Without background traffic, attack traffic is the only traffic on the network, which is unrealistic and trivially detectable. DETERLab's ExFiles and CyberVAN's traffic generation demonstrate the pattern. Background traffic is essential for realistic detection validation.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#436` (DSL-009: Run declared user-behavior profiles)
