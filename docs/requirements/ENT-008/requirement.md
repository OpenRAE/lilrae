---
id: ENT-008
title: "Docker-Mailserver Email Service"
status: ACTIVE
type: FUNCTIONAL
priority: COULD
wave: 3
created_at: 2026-03-20T06:11:22.991248Z
updated_at: 2026-03-20T06:18:11.649437Z
---

# ENT-008: Docker-Mailserver Email Service

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/ENT-008/requirement.md).


## Statement

The system shall provide an email server (docker-mailserver) on the DMZ (172.20.1.21) supporting SMTP (25), IMAP (143), and submission (587) protocols for the techvault.local domain.

## Rationale

Email is a standard enterprise service providing an additional attack surface.
