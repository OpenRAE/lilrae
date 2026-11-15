---
id: ENT-002
title: "Samba Active Directory Domain Controller"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 3
created_at: 2026-03-20T06:11:05.880770Z
updated_at: 2026-03-20T06:18:11.649310Z
---

# ENT-002: Samba Active Directory Domain Controller

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/ENT-002/requirement.md).


## Statement

The system shall provide a Samba AD domain controller (TECHVAULT.LOCAL) on the internal network (172.20.2.10) with 15+ user accounts including service accounts with SPNs (svc-sql, svc-backup), over-privileged accounts (svc-backup as Domain Admin), weak passwords, and anonymous LDAP bind enabled.

## Rationale

Active Directory provides the Path B attack surface.
