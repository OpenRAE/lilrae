---
id: RED-003
title: "Reverse Engineering Container"
status: ACTIVE
type: FUNCTIONAL
priority: COULD
wave: 3
created_at: 2026-03-20T06:11:36.047595Z
updated_at: 2026-03-20T06:18:11.649525Z
---

# RED-003: Reverse Engineering Container

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/RED-003/requirement.md).


## Statement

The system shall provide an Ubuntu-based reverse engineering container on the security network (172.20.0.27) with binary analysis tools (radare2, yara, capa, FLOSS), SSH access, and Wazuh agent.

## Rationale

Reverse engineering is a specialized analysis capability for malware analysis.
