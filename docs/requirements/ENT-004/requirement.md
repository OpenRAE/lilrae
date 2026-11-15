---
id: ENT-004
title: "SMB File Server with Open Shares"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 3
created_at: 2026-03-20T06:11:12.614043Z
updated_at: 2026-03-20T06:18:11.649352Z
---

# ENT-004: SMB File Server with Open Shares

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/ENT-004/requirement.md).


## Statement

The system shall provide a Samba file server on the internal network (172.20.2.12) with shares (Public, Shared, Engineering, IT-Backups) allowing anonymous/guest SMB access. Sensitive files including deploy.sh with plaintext credentials shall be accessible on open shares.

## Rationale

The file server provides the Path C entry point for credential harvesting.
