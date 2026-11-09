---
id: SEC-007
title: "Vetted-Author-Only Conversation Surface"
status: ACTIVE
type: NON_FUNCTIONAL
priority: MUST
created_at: 2026-05-16T22:39:15.372783Z
updated_at: 2026-05-16T22:39:56.079002Z
---

# SEC-007: Vetted-Author-Only Conversation Surface

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SEC-007/requirement.md).


## Statement

The repository's issue, pull-request, and discussion surfaces shall accept input only from vetted authors. Mechanism, scope, and lifetime of the control are operational details outside this requirement statement and outside any artifact change-controlled in this repository. Past content authored outside the vetted set shall be reviewed and curated where appropriate.

## Rationale

The repository's issue, pull-request, and discussion threads are consumed by both human maintainers and agent-assisted workflows that load historical thread content as context when responding to current work. Unrestricted authorship on those surfaces is a path for arbitrary external input to influence those downstream consumers; the requirement is the policy boundary that closes it.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-032-conversation-surface-hardening.md` (ADR-032: Conversation Surface Hardening)
- IMPLEMENTS → GITHUB_ISSUE `302`
- IMPLEMENTS → PULL_REQUEST `303`
