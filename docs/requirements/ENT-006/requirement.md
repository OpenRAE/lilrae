---
id: ENT-006
title: "Developer Linux Workstation"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 3
created_at: 2026-03-20T06:11:17.662104Z
updated_at: 2026-03-20T06:18:11.649395Z
---

# ENT-006: Developer Linux Workstation

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/ENT-006/requirement.md).


## Statement

The system shall provide a developer workstation on the internal network (172.20.2.40) with SSH access, Wazuh agent, development tools, and SSH keys that can be used for lateral movement to other hosts.

## Rationale

The workstation represents a developer endpoint with additional lateral movement paths.
