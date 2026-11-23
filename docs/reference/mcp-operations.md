# Connect MCP servers

Use an approved isolated lab VM with a selected, authorized scenario.
See the [MCP reference](mcp.md) for availability and service-selection limits.

## Setup And Verification

The normal path is automatic:

```shell
lilrae lab start --scenario <id>
lilrae lab status
```

After a usable startup, open the client from the project root.
Examine its connected servers and advertised tool lists. A simple read-only information
tool, such as `kali_info`, is a safer first check than a command or mutation.

## Build and verify artifacts

Use a source checkout in CI or an approved isolated test VM.
Build the shared library and all server artifacts:

```shell
./mcp/build-all-mcps.sh
```

Run targeted common-library and affected consumer checks in that runner.
Let CI perform complete consumer qualification.
Use `lilrae lab start` for normal operator startup and generated configuration.

## Narrow MCP selection

Read the [service-selection contract](mcp.md#scenario-service-selection).
Select only the authorized required services.
For an indexer/Wazuh-only selection, configure the existing fields:

```json
{
  "mcp": {
    "allowed_servers": ["aptl-indexer", "aptl-wazuh"],
    "required_servers": ["aptl-wazuh"]
  }
}
```

Examine admission failures before deployment.
Do not treat an omitted service as a startup error when it is intentionally outside the selection.

## Protect generated data

1. Keep `.env`, `.mcp.json`, private keys, bearer values, and target data out of issues and shared transcripts.
2. Use the generated TLS and authentication settings.
3. Keep certificate verification and the admitted authentication boundary intact.
4. Use `lilrae lab info` for observed endpoints and credential-file locations.
5. Keep tool operations within the selected authorized project.
