# Configure host MCP access

Use this How-to guide only in CI or an approved isolated lab VM.
See the [reference](host-mcp-access.md) for interface facts and limits.

## Guest enrollment

1. Start the canonical full pack with `lilrae lab start` in the approved lab VM.
2. Prepare a typed request with the [enrollment reference](host-mcp-access.md#guest-enrollment).
3. Select a new absolute output directory.
4. Run the enrollment command as the authorized guest operator:

```shell
lilrae mcp-access prepare-guest --request REQUEST.json --output-dir /absolute/new-directory
```

5. Configure the dedicated SSH account and listener through the existing supervisor.
6. Keep the account valid for public-key authentication with `UsePAM no`.
7. Disable password authentication through the generated policy and a non-password account record.
8. Restrict write access to authorized-key files and their ancestors.
9. Use only the generated `sshd_config` for this listener.

Do not append the enrolled keys to a general login account.
Keep generated private records within the approved guest-management boundary.
Continue with host configuration only after enrollment verifies the workload and capture.

## Host configuration

Use the authenticated seat-management channel.
Get the access record, public grant record, and SSH host public key. Compare the host-key SHA256 fingerprint with the independently obtained value. Then, from a private project directory, run this command:

```bash
lilrae mcp-access configure \
  --access-record /absolute/access.json --grant /absolute/caller.grant.json \
  --host-public-key /absolute/ssh_host_ed25519_key.pub \
  --expected-host-key 'SHA256:VERIFIED_FINGERPRINT' \
  --identity-file /absolute/host_transport_key --username aptl-mcp \
  --owner-id alice --seat-id seat-1 --instance-id instance-1 \
  --project-dir /absolute/project --client claude
```

Before you select the client, read the [client publication contract](host-mcp-access.md#client-publication-contract).
For Codex, repeat the command with `--client codex`.
Use the client's native project-trust and MCP approval procedure.
Before you retry publication, examine conflicting-entry or generation failures.
Do not overwrite manual edits to clear a conflict.

## Software integration checks

After you build the MCP packages, run this command:

```bash
bash tools/run-targeted-tests.sh tests/test_mcp_transport_processes.py tests/test_mcp_payload_processes.py -m integration -q
```

Examine discovery, revocation, runtime-identity, and browser-route results separately.
Read the [software integration evidence](host-mcp-access.md#software-integration-evidence) for what these checks prove.
They do not qualify a deployed lab or a new host profile.
