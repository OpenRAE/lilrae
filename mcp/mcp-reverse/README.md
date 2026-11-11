# Reverse engineering MCP

Use this How-to guide for an explicitly authorized SSH target.
The generic lab no longer gives a reverse workstation or `reverse` Compose profile.
The example target is disabled.
See the [component reference](../../docs/components/reverse-engineering-container.md) for current availability.

## Configure the target

1. Before you enable this server, select the authorized target.
2. Configure its host, port, user, SSH key, and container identity through the existing server configuration.
3. Enable the target only after those values identify the intended system.
4. Start the server through the approved project-aware MCP client.
5. Examine its connected tool list and input schemas.
6. Before you change target state, invoke a read-only information tool.

The shared SSH owner keeps validation and connection handling.
Retirement of the old Compose declarations removes no existing lab data or Docker volumes.
