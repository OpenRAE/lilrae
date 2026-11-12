# ADR-002: Wazuh SIEM over Splunk and qRadar

## Status

accepted

## Date

2025-08-06

## Context

The move from AWS to Docker required a different SIEM under [ADR-001](adr-001-docker-compose-deployment.md).
APTL v1.x used IBM qRadar Community Edition.
Version 1.1.0 also supported Splunk Enterprise through Terraform.
The comparisons below record the selection context, not current vendor terms.

### qRadar Community Edition

The recorded limits were 5,000 events per second and a renewable 30-day trial.
Installation needed a manually transferred 5 GB ISO and 1–2 hours.
The product needed a VM rather than a Docker image.
Its detection functions were useful, but its installation was too costly for the intended personal lab.

### Splunk Enterprise

The Terraform option used a c5.4xlarge instance.
The recorded free ingestion allowance was 500 MB per day.
Splunk supplied its UI and SPL search, and Docker images were available.
License administration still complicated lab use.
`siem_type` in `terraform.tfvars` selected the old SIEM.

### Requirements for v2.0

The replacement had these requirements:

- Docker containers instead of a required VM.
- Open-source software without lab license limits.
- Agent monitoring for host observations.
- Syslog collection for container application logs.
- OpenSearch or Elasticsearch indexing and a web investigation interface.
- An active community and rule ecosystem.
- A target below 4 GB RAM for the complete SIEM stack.

## Decision

Use Wazuh Manager, Indexer, and Dashboard as the SIEM.
The decision supports host observations, application logs, indexed queries, and a web interface without a trial clock.

### Wazuh Architecture

| Component | Recorded identity | Responsibility |
| --- | --- | --- |
| Manager | `aptl-wazuh-manager`, `172.20.0.10`, API 55000 | Process logs, evaluate rules, produce alerts, and collect across security, DMZ, and internal attachments |
| Indexer | `aptl-wazuh-indexer`, `172.20.0.12`, API 9200 | Store alerts, archives, and FIM data through OpenSearch |
| Dashboard | `aptl-wazuh-dashboard`, `172.20.0.11`, host 443 to container 5601 | Provide OpenSearch Dashboards with the Wazuh plugin |

The [root topology reference](../reference/compose-topology.md) states current compatibility declarations and exposure limits.
The [Wazuh reference](../components/wazuh-siem.md) describes maintained use.
A historical placement is not a guarantee for every admitted scenario.

### Dual Log Collection

Agent traffic uses TCP 1514.
The original design placed agents on victim and reverse-engineering containers for FIM, rootkit detection, auditing, and process observations.
Syslog uses UDP 514.
The design used rsyslog for web, database, authentication, and SOC application logs without an agent on every container.

The 2026-05-02 ADR-020 update records the #248 placement change.
It named `webapp`, `fileshare`, `ad`, `dns`, and `db` as five service targets.
Four used in-process agents so active response could apply iptables rules in the target namespace.
The PostgreSQL-on-Alpine `db` target kept a sidecar exception.
[ADR-020](adr-020-wazuh-agents-in-process-vs-sidecar.md) defines that decision and its later amendments.
These counts describe that update, not the current universal agent inventory.

### Version Pinning

The decision pinned the Wazuh components to 4.12.0.
Earlier mismatched agent and manager versions caused failures, recorded under CHANGELOG v3.0.13.
Current root Compose images still declare 4.12.0.
An installed scenario's declarations and qualified dependency set remain separate contracts.

## Consequences

### Positive

- The selected GPLv2 software removed the earlier EPS and trial-license limits.
- Official Docker images supported the local deployment model.
- Agent and syslog paths supplied complementary observations.
- OpenSearch queries supported the MCP Indexer integration.
- Community rules, Sigma conversion, and custom rules supported detection work.
- The original custom-rule scope included Falco, Kali, AD, web, Suricata, and database events.
- The API on 55000 supported programmatic management through MCP.

The historical rule scope does not prove that each source is present in the current pack.
The admitted scenario and collection configuration determine that evidence.

### Negative

- The design needed three SIEM containers and estimated about 4 GB RAM in total.
- The old record assigned 2 GB to the Indexer heap.
- Current root Compose instead declares a 1 GB initial and maximum JVM heap with a 2 GB container limit.
- Inter-component TLS requires certificate generation and distribution.
- Wazuh rule syntax requires different knowledge from Splunk SPL or qRadar AQL.
- Sigma rules require conversion, and the Dashboard has different investigation functions from the earlier alternatives.

### Risks

Version upgrades can break agent compatibility.
Pinning reduces accidental drift but requires deliberate upgrades.
OpenSearch and Elasticsearch differences can affect third-party API clients.
The added SOC integrations also increase Manager workload.
[ADR-063](adr-063-remove-thehive-and-cortex.md) removes the earlier TheHive integration from current TechVault delivery.
