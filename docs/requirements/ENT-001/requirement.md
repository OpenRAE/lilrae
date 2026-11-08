---
id: ENT-001
title: "Flask Web Application with OWASP Vulnerabilities"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 3
created_at: 2026-03-20T06:11:02.367863Z
updated_at: 2026-03-20T06:18:11.649290Z
---

# ENT-001: Flask Web Application with OWASP Vulnerabilities

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/ENT-001/requirement.md).


## Statement

The system shall provide a Flask web application on the DMZ network (172.20.1.20:8080) with intentional OWASP vulnerabilities: SQL injection on the login form and search API, command injection on the network tools page, information disclosure via exposed .env file and debug endpoint.

## Rationale

The web application provides the primary initial access vector.
