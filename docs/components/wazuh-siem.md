# Wazuh SIEM

Wazuh gives the manager, indexer, and dashboard for admitted scenarios that require them.
Scenario credentials are authored fixtures, separate from operator control-plane secrets.
Startup projects the admitted values into private runtime configuration.

## Components

| Component | Declared TechVault address | Responsibility |
| --- | --- | --- |
| Manager | `172.20.0.10` | The manager handles agent enrollment, log processing, detection rules, and alerts. |
| Indexer | `172.20.0.12` | The indexer gives OpenSearch storage and query services. |
| Dashboard | `172.20.0.11` | The dashboard gives a browser interface for investigation. |

The control plane can remap host ports.
`lilrae lab info` reports the observed endpoint and credential-file locations.
Default port numbers do not prove that a service is published.

## Data Flow

Agents send their declared logs to the manager.
The manager processes those events and forwards them through Filebeat to the indexer.
The dashboard queries the indexer.
The Wazuh and indexer MCP servers use the generated project connections.

## Wazuh Manager

The manager listens for agent traffic on TCP 1514, enrollment on 1515, syslog on UDP 514, and API requests on 55000.
Its declared network interfaces permit admitted agents to reach it.
The project renders secret-bearing configuration below `.aptl/config/`.
Tracked templates remain source-owned.

The manager loads bundled and scenario custom rules.
Response dispatch remains separate from detection.
See [active response](wazuh-active-response.md).

## Wazuh Indexer

The indexer uses OpenSearch on port 9200.
Alert indices use `wazuh-alerts-*`.
Archive indices use `wazuh-archives-4.x-*`.
Archive ingestion requires manager `logall` and `logall_json`, plus Filebeat's enabled archive fileset.

The template files are `config/wazuh_cluster/wazuh_manager.conf` and `filebeat_wazuh_module.yml` in the same directory.

## Wazuh Dashboard

The dashboard is a scenario browser service.
Its published port and admitted credentials come from the current deployment.
The participant desktop uses a certificate-valid hostname. Loopback is not the certificate identity.

## Falco Integration

Custom Falco rules remain detection content.
Their presence does not establish a running Falco sensor on the current victim.
See [victim monitoring](victim-containers.md#security-monitoring).

## MCP Integration

The generated Wazuh MCP handles manager operations.
The indexer MCP handles search and index operations.
The server's connected schema defines exact tool names and input fields.
See [MCP reference](../reference/mcp.md).

## Troubleshooting

See [inspect Wazuh services](wazuh-operations.md).
