# Host CLI access to an acquired full lab

**Legacy seat path:** New desktop seat images from issue #1178 run agents in
the guest and do not enroll this host MCP transport. This reference remains
for older signed seat images and the separate local integration workflow.

Host Claude Code and Codex use OpenSSH to carry MCP stdio to a fixed guest
`lilrae mcp-access dispatch` command. The user's provider login stays in the host
client account. The transport enrolls a separate Ed25519 public key. It does
not copy provider authentication to the guest. MCP execution, service keys,
capture, artifact access and Docker authority remain in guest management.

## Guest enrollment

The enrollment record binds the selected pack's exact identity and digest.
A later pack change invalidates the grant.
TechVault and its participant-study copy use the same enrollment interface.
The output directory must be new and absolute.
See [enroll the guest](host-mcp-operations.md#guest-enrollment) for the procedure.
The typed request contains:

- `owner_id`, `seat_id`, `instance_id`, positive `generation`.
- separate `guest_endpoint` and `outer_endpoint` objects, each with a loopback
  `address` and TCP `port`.
- absolute `project_dir`, `management_home`, `docker_socket`, `node_executable`,
  `aptl_executable`, `host_key` and `host_public_key` paths.
- the dedicated SSH `username`, with `/bin/sh` and a management-owned home.
- `keys`, each with a unique `grant_id`, Ed25519 `public_key`, `profile` (`red`
  or `blue`) and timezone-aware `expires_at` no more than 24 hours away.
- `delivery: rootful-integration` for controlled local software integration, or
  `delivery: appliance` with `appliance` paths to the verified launch descriptor,
  release/qualification public keys and fresh runtime boundary observation.

Enrollment proves the full live workload and capture before it writes private
`binding.json`, `access.json`, individual grant records, `authorized_keys` and
`sshd_config`. The dedicated listener uses only that generated configuration.
The generated keys do not authorize a general login account.

The downstream supervisor owns user/key creation, listener startup, file ownership and outer port mapping.
The account must be valid for public-key login with `UsePAM no`. OpenSSH rejects a locked account before key authorization. The generated policy disables password login.
The dedicated account must have a non-password account record.

Authorized-key paths and their ancestors must not permit group or other write access.
The dispatcher runs as a trusted guest service identity with the selected
backend's management access. Participants receive no general login to it.

The listener permits public-key authentication and a forced selector only:
`aptl-mcp-v1 INSTANCE GENERATION SERVER`. It denies PTYs, forwarding, agent
forwarding, passwords, environment injection, user rc files, SFTP and arbitrary
commands. Guest management paths and backend argv are never participant inputs.

## Host configuration

See [Configure host MCP access](host-mcp-operations.md#host-configuration).

## Discovery, authority and lifecycle

`aptl.seat-access/v1` contains owner, seat, instance, generation, guest boot, Docker daemon, project, and full 64-hex container identities. It also contains installed pack identity, distinct guest/outer endpoints, host-key fingerprint, UTC observation time, and lifecycle state. It contains no secrets and grants no authority. Host setup
must have `ready` and an observation at most 120 seconds old.

The guest binding and enrolled key establish authority. Each operation rechecks
caller identity, expiry/revocation, role, unchanged runtime identity and required
capture. Appliance delivery also examines the signed host-MCP contract and
boundary evidence at most five seconds old. A changed endpoint or reset needs a
new generation, regenerated enrollment and refreshed host configuration.
`lilrae mcp-access refresh --binding PATH --output PATH` refreshes discovery only.
`lilrae mcp-access revoke --binding PATH --grant-id ID` revokes active and future
connections.

Refresh cannot extend a grant.

Concurrent MCP servers share the guest lifecycle observation lock. These reads
exclude start/reset mutations, and an active lifecycle mutation rejects access.

The relay verifies the exact canonical tool inventory before it returns MCP initialization. It supports tool listing/calls, ping and lifecycle notifications.
The relay denies resources, prompts, sampling and server-initiated requests.
Its limits are:
1 MiB frames, eight queued requests, 120-second calls, 300-second idle timeout,
one-hour connection lifetime, 64 MiB output and one process per instance/server.

Revocation closes the connection and stops its process group. Strict remote
SSH teardown must acknowledge closure. Otherwise a private taint blocks reuse
until operator recovery creates a clean generation. Do not remove a taint as a substitute for proof of remote cleanup.

Tool schemas keep their JSON Schema structure. Terminal session handles
remain available to the caller for subsequent commands and closure. API login
sessions, service credentials and secret-shaped command output stay redacted.

## Software integration checks

See [Configure host MCP access](host-mcp-operations.md#software-integration-checks).

## Appliance-seat integration

Older signed seat images carried this contract through their VM management channel.
New desktop images do not enroll this host transport. The legacy launcher publishes a nonce-bound enrollment request in its read-only launch share. It accepts the response only on the private generation-specific socket. It persists the owner-only access bundle and writes the selected client configurations.

Stop and failed start invalidate the generation. Reset destroys the overlay, rotates instance/generation state, and must have new client material. Calls made with stale files therefore fail. They do not silently reach a replacement seat.

Production qualification invokes a read-only tool through both native client configurations. It proves revocation after stop, resets the seat, and records current guest/container identities. The two-seat machine-A drill and distinct machine-B drill remain separate signed evidence. Unit protocol tests and two VMs on one machine do not replace those drills.

## Software integration evidence

These checks start an ordinary-user OpenSSH listener on an allocated loopback
port. They exercise the production dispatcher and relay with built MCP processes. Cases cover red discovery, a blue indexer query against controlled HTTPS, revocation, runtime identity mismatch, and the browser WebSocket route. Deployment and capture observations are fixtures. The checks
do not access Docker, alter host limits or qualify a deployed lab.

The payload tests initialize all seven MCP servers from archived and extracted
build outputs after they remove their temporary source tree. Flattened common-library
packages keep their own dependencies so runtime imports remain self-contained.
The tests give a fresh public CA after extraction for services that require
runtime trust material. They make no service calls.

The checks workflow runs this suite after it builds the MCP packages. The
clean-install job uses the smaller scenario to cover package materialization
and the install/start/teardown lifecycle. Full TechVault tests are triggered
manually during related development. They are intentionally separate from
routine CI because running the full lab on every change is too costly.

Client-driven checks used Claude Code 2.1.274 and Codex 0.154.0 to invoke
`kali_info` through the generated SSH entries. Both returned the built backend's
`target_name: Kali Linux` and `ssh_user: kali`. Codex also exercised its native
app-server MCP call interface. Headless Codex must have explicit approval for the
selected MCP tool.

This check approved only `kali_info` for that invocation.
Provider authentication stayed in the host client account. These checks prove
client/transport interoperability, not command execution in a booted guest.

## Client publication contract

| Client selection | Generated file |
| --- | --- |
| `--client claude` | `.mcp.json` |
| `--client codex` | `.codex/config.toml` |

Provider authentication remains in the native client's host account.
Generated SSH entries use a private known-hosts file for each generation.
They enforce `StrictHostKeyChecking=yes`, disable agent access and multiplexing, and use `-F /dev/null`.

Regeneration keeps manual settings and records exact managed-entry ownership.
Conflicting edits, duplicate JSON keys, stale generations, and another owner's instance prevent publication. Configuration remains unchanged.
A new generation is necessary for a changed host pin.
A locked write-ahead journal recovers interrupted publication.

`.aptl` and `.codex` state directories must be caller-owned with mode `0700`.
The generated target configuration uses mode `0600`.
The client's native project-trust and MCP approval controls still apply.
