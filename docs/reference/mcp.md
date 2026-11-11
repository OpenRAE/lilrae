# MCP Reference

APTL's Model Context Protocol servers let an authorized AI client operate the
red- and blue-team surfaces realized by a scenario. `lilrae lab start` builds the
artifacts needed by that scenario and creates or updates the project-private
`.mcp.json` client configuration.

Project-aware clients read generated configuration from the lab project directory.
LilRAE keeps existing client entries when it updates its managed entries.
`.mcp.json` can contain API credentials, resolved ports, and transport settings.

## Server Availability

| Artifact | Generated client entry | Tool prefix | Default client config | Target |
| --- | --- | --- | --- | --- |
| `mcp-indexer` | `aptl-indexer` | `indexer` | yes | Wazuh Indexer search and index operations |
| `mcp-network` | `aptl-network` | `network` | yes | Network IDS observations exposed through the lab APIs |
| `mcp-red` | `aptl-red` | `kali` | yes | Kali information, commands, and bounded sessions |
| `mcp-reverse` | `aptl-reverse` | `reverse` | no | Optional reverse-engineering container sessions |
| `mcp-soar` | `aptl-soar` | `soar` | yes | Shuffle workflow and response operations |
| `mcp-threatintel` | `aptl-threatintel` | `threatintel` | yes | MISP threat-intelligence operations |
| `mcp-wazuh` | `aptl-wazuh` | `wazuh` | yes | Wazuh manager alerts, agents, and rules |

The table distinguishes three separate facts:

1. A **built artifact** exists in the released project assets.
2. A **generated client entry** is present only when APTL configures that
   server for the project and realized scenario.
3. An **advertised tool** is the fully qualified name returned by the connected
   server.

Do not treat the artifact list as proof that every server is active. The
optional reverse server, for example, is built but is absent from the default
client configuration unless the realized scenario gives its target.

## Tool Names And Behavior

Tool names use the server's prefix. SSH-backed servers advertise names such as
`kali_info`, `kali_run_command`, `kali_interactive_session`, and
`kali_get_session_output`. `run_command` by itself is not an APTL tool name.
API-backed servers advertise prefixed information, query, and action tools such
as `wazuh_api_info` or a server-specific qualified query name.

The connected server's tool list and input schema are authoritative for the
installed release. Tool availability can vary with the scenario, target
configuration, and server type. An unavailable target returns a bounded error.
The client must not bypass that result with direct credentials or an
undocumented network call.

## Setup And Verification

See [connect MCP servers](mcp-operations.md).

## Security Boundary

Generated credentials, private keys, bearer values, and target-bearing tool results are private project data.
The effective TLS, authentication, endpoint, and target settings come from generated configuration.
An unavailable target returns a bounded error.
Direct credential use or an undocumented network request does not override that refusal.

See [MCP operation](mcp-operations.md) for setup and data-handling steps.
See [MCP integration](../components/mcp-integration.md) for component contracts.

## Scenario service selection

A run exposes only MCP servers whose service bindings exist in its exact admitted
scenario. Family trials use their instantiated snapshot, so a selected-out MISP
service has no threat-intelligence MCP server, credentials, or endpoint binding.
The shipped operator catalog is `src/aptl/core/participant_mcp_policy.json`.
Scenario packs cannot add artifacts or widen its role ceilings.

`mcp.allowed_servers` narrows the operator's server selection.
`mcp.required_servers` names servers that must be admissible.
The [selection procedure](mcp-operations.md#narrow-mcp-selection) gives a bounded configuration example.

A required server without its declared services rejects admission before
deployment. A selected server whose live endpoint or credential is unavailable
fails startup. An intentionally omitted service is simply absent from discovery.

Each run replaces managed MCP entries and endpoint bindings. Guest discovery and
server dispatch apply that selection as well as the enrolled role. Older seat records without an explicit MCP selection grant no MCP access.
The [enrollment procedure](host-mcp-operations.md#guest-enrollment) creates a replacement transport binding.
