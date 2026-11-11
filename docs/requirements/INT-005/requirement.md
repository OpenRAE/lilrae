---
id: INT-005
title: "Sigma Rule Pipeline"
status: DRAFT
type: FUNCTIONAL
priority: WONT
wave: 2
created_at: 2026-03-21T07:52:04.691079Z
updated_at: 2026-10-09T00:00:00.000000Z
---

# INT-005: Sigma Rule Pipeline

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/INT-005/requirement.md).


## Statement

The platform shall provide a Sigma rule pipeline using pySigma to compile Sigma rules into Wazuh XML rules and Suricata signatures, enabling import and use of the 3,000+ community Sigma rules.

## Rationale

WITHDRAWN 2026-10-09: The issue closed as not planned on 2026-07-19 without a closing comment. See GitHub issue #446. --- Original rationale: pySigma has a Wazuh backend. The 3,000+ community Sigma rules represent years of detection engineering knowledge. A compilation pipeline makes this immediately available without manual rule translation.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#446` (INT-005: Sigma Rule Pipeline)
