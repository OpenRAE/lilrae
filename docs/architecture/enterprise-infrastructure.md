# Minimum Viable Enterprise + Agentic SOC

This Explanation describes the reasons for the enterprise lab design.
It separates those reasons from the original delivery plan.
The admitted Scenario Pack determines the actual service set.
Root Compose stubs do not establish installed behavior.

[ADR-063](../adrs/adr-063-remove-thehive-and-cortex.md) removed TheHive, Cortex, and case-management integration.
The lab has no replacement case-management tool.
The earlier Windows endpoint subnet and Caldera proposal do not establish shipped capabilities.
The [Windows reference](../reference/windows-endpoint.md) states the supported endpoint boundary.

## Where We Started

The early lab combined Wazuh, a Linux victim, Kali, a reverse-engineering container, and MCP servers.
The Python CLI controlled its lifecycle.
A single target could not represent identity attacks, application dependencies, or movement between enterprise services.
The expanded design added distinct services so an exercise could produce related host, application, and network observations.

The original proposal described four delivery phases.
That plan remains historical context; phase numbers are not current qualification results.
The earlier claim that phases 1–3 were complete included planned Windows work and is not a reliable completion statement.

## The Core Design Question

The design sought a small enterprise environment with useful attack paths and enough telemetry for defensive investigation.
It used three representative attack chains:

- Web compromise, privilege escalation, lateral movement, and data exfiltration.
- Credential theft, identity abuse, and domain compromise.
- Service misconfiguration, initial access, persistence, discovery, and movement to another host.

These chains explain the selected service roles.
They do not prove attack coverage or establish that every technique works.

### Enterprise service roles

| Service | Design reason | Original proposal and limit |
| --- | --- | --- |
| Samba AD DC | Provide identity, Kerberos, LDAP, and domain relationships | The proposal specified `techvault.local`, 10–15 accounts, groups, OUs, weak passwords, and selected SPNs. Actual declarations belong to the installed pack. |
| TechVault portal | Give web attacks an application and database context | The proposal included login, upload, API, and administration functions with SQL injection, XSS, IDOR, and weak authentication. An exact vulnerability needs scenario evidence. |
| PostgreSQL | Provide application data and a collection target | The proposed schema included users, password hashes, customer data, file metadata, API keys, and audit logs. The pack owns seed data. |
| Mail | Support phishing exercises and credential reuse | The proposal used Postfix and Dovecot for the same 10–15 users. The root Compose file no longer declares this service. |
| Samba file server | Provide shares, access-control problems, and collection targets | The proposal included engineering, finance, and HR shares with planted credentials, database backups, and SSH keys. These are scenario facts, not platform defaults. |
| DNS | Support internal resolution and observable queries | The proposal used Bind9 for `techvault.local`. Query evidence can support detection exercises; it does not prove DNS-tunneling detection. |
| Linux victim | Provide host-level attacks and observations | The early proposal used Rocky Linux, SSH, cron, sudo and SUID problems, auditd, Falco, and Wazuh. Current substrates follow admitted node declarations. |
| Windows endpoint | Support domain-joined endpoint exercises | The proposal specified Windows 11, employee files, browser history, saved credentials, Sysmon, PowerShell logs, Wazuh, and optional XSIAM. This list is historical intent. |

The early web alternative was DVWA or Juice Shop with TechVault branding.
The design favored a realistic application context over a generic isolated vulnerability.
That choice did not authorize a new upstream application or commercial service.

### Detection and response roles

Wazuh supplies host and application event collection and rule evaluation.
Suricata supplies network observations that host logs alone cannot provide.
[ADR-019](../adrs/adr-019-suricata-ids-only-prevention-via-wazuh-ar.md) keeps Suricata in IDS mode and assigns packet blocking to Wazuh active response.
The collection configuration determines how Eve JSON reaches the SIEM.
The original proposed Filebeat path is not a universal ingestion contract.

MISP supplies structured threat indicators.
The original alternatives included OpenCTI, but the selected design used MISP and its existing integration path.
[ADR-022](../adrs/adr-022-misp-driven-suricata-rules.md) explains indicator-driven Suricata rule synchronization.
Feed names in the proposal, including abuse.ch, OTX, and CIRCL, do not prove enabled live feeds.

Shuffle supplies the selected SOAR integration.
The proposal considered n8n but preferred a security-specific workflow system.
A proposed response, such as account disablement or host isolation, requires an implemented workflow and qualification.
Its appearance in this design is not a delivered action contract.

TheHive originally supplied cases, observables, timelines, reports, and Cortex analyzer calls.
Cortex supplied enrichment for that case workflow.
ADR-063 records their removal and its license rationale.
Historical attack-to-case evidence remains historical; it does not describe the current service set.

Caldera remained an optional adversary-emulation proposal.
The design proposed ATT&CK-mapped profiles and a possible MCP extension.
It did not establish an installed Caldera integration.

### MCP ownership

The common MCP layer provides shared transport and tool dispatch.
Server configuration selects existing SSH and API tools.
[ADR-003](../adrs/adr-003-mcp-common-library.md) explains that reuse.
The [MCP reference](../reference/mcp.md) lists supported interfaces.

The original plan named red-team, Wazuh, Indexer, reverse-engineering, threat-intelligence, case-management, SOAR, and network servers.
`mcp-casemgmt` and its `cases_*` tools were removed with TheHive.
A historical server list is not the current installed inventory.

## Network Segmentation

The design separates security, DMZ, internal, and red-team networks.
The [network explanation](networking.md) describes their purpose and limitations.
The [root topology reference](../reference/compose-topology.md) owns compatibility subnets and addresses.

The proposed endpoint network was `172.20.3.0/24`.
Its presence in the old diagram did not prove realization.
The earlier design placed Kali only in the DMZ and required a pivot for internal access.
The compatibility declarations attach Kali directly to red-team, DMZ, and internal networks.
The current Explanation therefore makes no pivot-enforcement claim.

### Deployment and resource trade-offs

Containers reduced the cloud dependency and supported a small local lab.
They still share host resources and a kernel.
[ADR-060](../adrs/adr-060-vm-only-seat-containment.md) assigns disposable seat containment to a VM.
A container network is not that containment boundary.

The original resource estimate used these figures:

| Historical estimate | RAM |
| --- | --- |
| Early APTL baseline | About 5 GB |
| Added enterprise services | 4–5 GB |
| Added security stack | 6–8 GB |
| Optional Windows VM | 4–6 GB |
| Stated full-stack total | 20–24 GB |

The proposal suggested a 32 GB host and described 64 GB as comfortable.
Its component estimates included MISP at about 2 GB, TheHive at about 2 GB, Shuffle at about 1 GB, and Suricata at about 1 GB.
It also estimated expanded Wazuh at about 2 GB.
These figures were planning estimates, not a measured current capacity contract.
[Host requirements](../getting-started/host-requirements.md) owns current guidance.

### Original delivery phases

| Phase | Proposed work | Present interpretation |
| --- | --- | --- |
| 1: Enterprise attack surface | AD, seeded PostgreSQL, vulnerable portal, segmentation, Wazuh rules, and Suricata | Service intent; delivery and qualification depend on admitted scenario evidence |
| 2: SOC tooling | MISP feeds, TheHive templates, Shuffle playbooks, four new MCP integrations, IOC matching, and active response | Partly superseded by ADR-063; no current case-management claim |
| 3: Extended enterprise | Mail, file server, domain-joined Windows, DNS, and Caldera | Original scope; no blanket phase-completion claim |
| 4: Autonomous purple team | Scenario engine, ATT&CK mapping, attack/detect scoring, coverage analysis, reports, and 10–20 attack chains | Historical target; each capability needs its own implemented contract and evidence |

The original proposal estimated Samba could cover 80% of AD use cases.
It supplied no qualification method for that percentage.
Samba and Windows Server AD are therefore distinct choices, with technique-specific compatibility that requires evidence.
The proposal's other alternatives were MISP/OpenCTI, Shuffle/n8n, Suricata/Zeek, custom portal/generic application, and optional Windows.
The selected architecture and later ADRs determine current choices.
