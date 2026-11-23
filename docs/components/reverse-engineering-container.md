# Reverse Engineering Container

The generic lab no longer gives a reverse workstation or a `reverse` Compose profile.
The optional `mcp-reverse` artifact remains available for an explicitly configured SSH target.
Its example target is disabled.

The [source record](records/reverse-engineering-container-2026-11-06.txt) keeps the earlier image description at revision `28fc8f18`.
That description does not establish a current image, address, port, tool installation, or Wazuh agent.
Status reviewed: 2026-11-06.

## Container Configuration

An operator gives the authorized target and its software.
There is no current `containers/reverse/Dockerfile` in this repository.

## Network Access

No reverse workstation publishes host port 2027 by default.
The target's configured endpoint determines access.

## MCP Integration

The server uses tool prefix `reverse` and the shared SSH connection owner.
See [configure the reverse MCP](https://github.com/OpenRAE/lilrae/blob/dev/mcp/mcp-reverse/README.md) for target requirements.
See [MCP availability](../reference/mcp.md#server-availability) for the built artifacts.

## SIEM Integration

The optional MCP server does not establish Wazuh enrollment for an external target.
The target owner must give and verify any monitoring separately.
