---
id: DET-005
title: "Cross-Source Detection Correlation"
status: DRAFT
type: FUNCTIONAL
priority: WONT
wave: 3
created_at: 2026-03-21T07:49:55.662255Z
updated_at: 2026-10-09T00:00:00.000000Z
---

# DET-005: Cross-Source Detection Correlation

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/DET-005/requirement.md).


## Statement

The platform shall correlate detections across multiple sources (for example, Wazuh host-based alert + Suricata network alert) within configurable time windows to identify multi-signal attack patterns that no single source would detect.

## Rationale

WITHDRAWN 2026-10-09: The issue closed as not planned on 2026-07-27 without a closing comment. See GitHub issue #470. --- Original rationale: SOC-006 describes end-to-end workflow integration but not automated cross-source temporal correlation. Real SOC analysts correlate across sources; the platform should automate and score this.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#470` (DET-005: Cross-Source Detection Correlation)
