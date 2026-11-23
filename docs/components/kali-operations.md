# Operate the Kali node

Use an approved isolated lab VM and the admitted scenario's declared access routes.
The [Kali reference](kali-redteam.md) defines capture, custody, endpoints, and redaction behavior.

## Use required capture

1. Examine the connected red MCP tool list and input schemas.
2. Use its admitted information or command tools for the selected node.
3. Keep the active run and session identities through the generated configuration.
4. Before you claim complete terminal evidence, examine capture-harvest failures.

Do not replace required captured access with a direct shell.

## Access without required capture

Before direct access, make sure that the admitted scenario has no capture sidecar requirement.
Discover the current relay port through `lilrae lab info`.
If the declared port remains 2023, the host SSH command is:

```shell
ssh -i ~/.ssh/aptl_lab_key -p 2023 kali@localhost
```

For the supported container shell route, run this command:

```shell
lilrae container shell aptl-kali
```

The control plane refuses both routes when they cannot meet the active capture contract.
Do not treat a refused plain SSH session as an invitation to bypass capture.

## Configure experimental redaction

Use this option only when the experiment's signal consists of credential values.
Keep the collected data within the approved evidence boundary.

1. Read the [redaction contract](kali-redteam.md#experimental-record-redaction-toggle).
2. Set `APTL_EXPERIMENT_NO_REDACT=1` in the selected MCP server's environment.
3. Start the server through its existing approved launcher.
4. Before you collect evidence, examine the experiment's retained data policy.
5. Before you return to ordinary redacted capture, remove the setting.

The setting does not grant permission to publish credentials or captured content.
