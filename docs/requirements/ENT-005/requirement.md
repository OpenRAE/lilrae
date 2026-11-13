---
id: ENT-005
title: "Rocky Linux Victim Server"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 3
created_at: 2026-03-20T06:11:15.338215Z
updated_at: 2026-03-20T06:18:11.649374Z
---

# ENT-005: Rocky Linux Victim Server

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/ENT-005/requirement.md).


## Statement

The system shall provide a Rocky Linux victim server on the internal network (172.20.2.20) with SSH access, Wazuh agent, a labadmin user with sudo NOPASSWD, and CTF flags at /home/labadmin/user.txt and /root/root.txt.

## Rationale

The victim server is the primary lateral movement target.
