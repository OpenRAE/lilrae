---
id: UI-006
title: "Web GUI Product Scope"
status: ACTIVE
type: NON_FUNCTIONAL
priority: SHOULD
wave: 5
created_at: 2026-06-23T04:29:36.514981Z
updated_at: 2026-06-23T04:30:19.228322Z
---

# UI-006: Web GUI Product Scope

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/UI-006/requirement.md).


## Statement

The APTL web GUI shall have a documented product scope that defines its target users, the jobs it serves beyond the MCP-driven purple loop and the CLI, the in-scope capabilities for a v1 surface, its authentication and security posture, and its shipping model (in particular whether the built app is served by `aptl web serve`). The scope shall serve as the acceptance baseline for the web GUI design (UI-007) and implementation (UI-008).

## Rationale

The existing web frontend is a paused MVP spike (UI-001 workbench, UI-003 terminal, SYS-010 notebook MVP): a three-page SvelteKit app that is dev-served, not bundled into `aptl web serve`, and not the authentic MCP-driven product surface. Before further investment, the web GUI needs a deliberate product definition rather than incremental button-completion. This requirement also gates DET-003 (Live SIEM Query Execution), which overlaps RTE-001's automated objective-query evaluation and should not be built until the GUI's role is decided.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `539` (UI-006: Scope the APTL web GUI as a product surface)
