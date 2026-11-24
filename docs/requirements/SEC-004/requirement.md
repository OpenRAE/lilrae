---
id: SEC-004
title: "TLS Between Wazuh Components"
status: DEPRECATED
type: NON_FUNCTIONAL
priority: SHOULD
wave: 1
created_at: 2026-03-20T06:10:10.173444Z
updated_at: 2026-11-12T07:31:45.000000Z
---

# SEC-004: TLS Between Wazuh Components

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SEC-004/requirement.md).


## Statement

All Wazuh inter-component communication (Manager to Indexer, Dashboard to Indexer, Dashboard to Manager API) shall use TLS with generated certificates. The MCP common library's HTTPClient shall use per-request `https.Agent` with rejectUnauthorized: false for self-signed lab certificates, not process-global NODE_TLS_REJECT_UNAUTHORIZED.

## Rationale

Per-request SSL handling prevents the security anti-pattern of globally disabling certificate verification.
