---
id: ENT-009
title: "Intentional Security Misconfigurations"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 3
created_at: 2026-03-20T06:11:27.492322Z
updated_at: 2026-03-20T06:18:11.649459Z
---

# ENT-009: Intentional Security Misconfigurations

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/ENT-009/requirement.md).


## Statement

The enterprise environment shall include deliberate security gaps modeled on OWASP Top 10 patterns: no WAF (A03), no database network ACLs (A05), guest SMB access (A05), no MFA (A07), weak passwords (A07), limited automated response (A09), over-privileged service accounts (A01), and credential sprawl (A05).

## Rationale

A security training lab must have realistic, intentional vulnerabilities.
