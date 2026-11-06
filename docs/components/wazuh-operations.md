# Inspect Wazuh services

Use an approved isolated lab VM with a running admitted scenario.
See the [Wazuh reference](wazuh-siem.md) for component and data-flow facts.

## Troubleshooting

1. Examine `lilrae lab status` and the startup diagnostics.
2. Use `lilrae lab info` for observed endpoints and credential-file locations.
3. Examine the realized manager's bounded logs with `lilrae container logs`.
4. Examine agent enrollment through the generated Wazuh MCP connection.

5. Query the indexer through its generated authenticated connection.
6. Make sure that fresh events carry the expected agent identity.

If archive indices are absent, examine the manager's archive settings and Filebeat archive fileset.
A running manager or a connected agent does not prove that a particular event reached the indexer.
Keep authentication values out of command arguments and shared evidence.
Use the generated trust settings. Do not disable certificate verification for diagnosis.
