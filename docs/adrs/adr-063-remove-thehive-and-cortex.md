# ADR-063: Remove TheHive and Cortex from the TechVault SOC Stack

## Status

accepted

Owner decision on [issue #1411](https://github.com/OpenRAE/lilrae/issues/1411).
This ADR supersedes the TheHive and Cortex decisions in
[ADR-008](adr-008-soc-stack-integration.md). The MISP, Shuffle, and Suricata
decisions in ADR-008 remain in force.

## Date

2026-10-30

## Context

ADR-008 added TheHive 5 for case management and Cortex for observable
enrichment. ADR-008 describes TheHive as open source. TheHive 5 is proprietary
StrangeBee software. TheHive 4, the last open-source release, is archived.

TheHive 5.3 and later starts a 14-day trial at first installation. After the
trial, TheHive is read-only until it has a valid license
([About licenses](https://docs.strangebee.com/thehive/installation/licenses/about-licenses/)).
A license applies to one instance. An operator copies a challenge from TheHive
to the StrangeBee portal and applies the generated key in TheHive
([Activate or update a license](https://docs.strangebee.com/thehive/installation/licenses/license/)).

The free Community license permits only non-commercial use and at most 2 users
([TheHive Community license](https://strangebee.com/thehive-community-license/)).
Its general terms grant one copy and prohibit distribution
([TheHive 5 General Terms, Community Version](https://strangebee.com/wp-content/uploads/2024/06/TheHive-5-Community-License-General-Terms-latest.pdf),
sections 1.1 and 1.3).

Issue #1411 records the effect on TechVault. After the trial, TheHive permits
no Cortex connection. The required `cortex-enrichment-readback` evidence then
fails, lab start fails, and the seat launcher stops the guest. Each seat
overlay and each lab volume set is a new installation, so the failure occurs
again after 14 days on each one.

Cortex is open source (AGPL-3.0) and needs no license. In TechVault, Cortex
runs one offline analyzer, `TechVaultScenarioContext_1_0`. The analyzer
reports whether an IP is `172.20.1.30`. MISP already holds that IP as a
seeded IOC. TheHive and the readiness check are the only consumers of Cortex.
No MCP server calls Cortex.

The TechVault pack declares TheHive and Cortex. LilRAE realizes the admitted
pack without rewriting the scenario
([ADR-059](adr-059-canonical-techvault-delivery-and-host-mcp-access.md)).

## Decision

Remove TheHive and Cortex from the TechVault SOC stack. The lab has no
case-management tool.

- The TechVault pack removes TheHive, Cortex, their datastores, accounts, and
  relationships, and the `cortex-enrichment-ready` proposition and its
  evidence requirement
  ([OpenRAE/env-packs#536](https://github.com/OpenRAE/env-packs/issues/536)).
- LilRAE removes its TheHive and Cortex realization, the `mcp-casemgmt`
  server, and the Wazuh to Shuffle to TheHive integration when it adopts that
  pack release.

TheHive is removed because of its license terms. Without TheHive, Cortex gives
the lab almost nothing: its only analyzer repeats an IOC that MISP holds.

## Consequences

### Positive

- The lab has no vendor license clock. Readiness no longer fails 14 days after
  installation.
- The lab runs four fewer containers: `thehive`, `thehive-cassandra`,
  `thehive-es`, and `cortex`.

### Negative

- Blue agents and participants have no structured case tracking. The
  `cases_*` MCP tools are removed.
- The Wazuh to Shuffle to TheHive integration is removed. This integration is
  disabled at first boot.
- Installations that adopt the new pack lose access to their TheHive cases and
  Cortex jobs.
- Workshop and participant documents that use TheHive or Cortex need changes.
