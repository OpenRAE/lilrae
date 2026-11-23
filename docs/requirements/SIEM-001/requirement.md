---
id: SIEM-001
title: "Host-Level Monitoring via Wazuh Agents"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-03-20T06:10:16.877657Z
updated_at: 2026-10-12T18:00:18.618385Z
---

# SIEM-001: Host-Level Monitoring via Wazuh Agents

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SIEM-001/requirement.md).


## Statement

The system shall deploy Wazuh agents on SSH-enabled containers (victim, workstation, reverse, kali) to provide host-level visibility including file integrity monitoring, rootkit detection, system call auditing, and process monitoring via port 1514/tcp.

## Rationale

Agent-based monitoring provides host-level telemetry that syslog cannot.

## Traceability

- IMPLEMENTS → ADR `docs/adrs/adr-002-wazuh-siem.md` (ADR-002: Wazuh SIEM)
- IMPLEMENTS → GITHUB_ISSUE `248` (Issue #248: in-process Wazuh agents on webapp/fileshare/ad/dns (replaces sidecar pattern))
- IMPLEMENTS → ADR `docs/adrs/adr-020-wazuh-agents-in-process-vs-sidecar.md` (ADR-020: Wazuh agents run in-process on the target containers)
- IMPLEMENTS → CODE_FILE `containers/_wazuh-agent/install.sh` (Shared Wazuh agent apt-install helper (sidecar + in-process targets))
- IMPLEMENTS → CODE_FILE `containers/_wazuh-agent/wazuh-agent.sh` (Shared Wazuh agent runtime bootstrap (registers, starts daemon, supervises))
- IMPLEMENTS → CODE_FILE `containers/_wazuh-agent/ossec.conf.template` (Shared Wazuh agent ossec.conf template)
- IMPLEMENTS → CONFIG `config/wazuh_cluster/wazuh_manager.conf` (Wazuh manager: &lt;auth&gt;&lt;force&gt; allows in-process takeover from sidecar)
- TESTS → TEST `tests/techvault/test_in_process_agents.py` (Realized workload substrates and rendered Wazuh agent identity, manager and log-source contracts)
- IMPLEMENTS → GITHUB_ISSUE `249` (Issue #249: extends in-process agent platform's AR-execution surface (wrapper deploys to every agent))
