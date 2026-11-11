# ADR-040: Terminal SSH Host-Key Verification Boundary

## Status

accepted

## Date

2026-06-13

## Reader boundary

This Explanation records design reasons and constraints.
Dated examples, versions, estimates, and measurements describe their stated revision.
They do not establish current interface support or installed qualification.
The [web Reference](../reference/web.md) describes maintained use.
The record's status and amendments still determine its decision scope.

## Context

Issue #418 identifies that the operator-facing WebSocket terminal relay opens
its `asyncssh` client connection with `known_hosts=None`. That disables SSH
server host-key verification on the connection that carries the operator's
interactive PTY input.

The original relay dialed loopback or lab-local targets. Its route already required an allowed WebSocket Origin, an allowed container, and a running lab. The boundary
is still control-plane: if an attacker can impersonate the SSH endpoint the
relay dials, the relay will stream whatever the operator types.

Relevant incumbents already exist:

- `src/aptl/api/routers/terminal.py` owns the WebSocket terminal route,
  Origin check, terminal error envelope, and `asyncssh` connection.
- `src/aptl/core/endpoints.py` and ADR-036 own canonical endpoint metadata and
  runtime SSH reachability decisions; host-published ports must not be
  duplicated in another registry.
- `src/aptl/core/lab.py` owns ordered lab startup, generated-artifact material,
  and bind-mount preflight timing.
- `src/aptl/core/ssh.py` owns the operator client key pair and distribution of
  public keys into target `authorized_keys`.
- `src/aptl/core/deployment/` and ADR-037 own Docker/Compose interaction
  through `DeploymentBackend`.
- ADR-028 owns generated runtime artifact placement and containment under the
  ignored project state tree.
- ADR-029 owns classification, redaction, and serialization boundaries for
  operator/control-plane secrets.

## Decision

The WebSocket terminal relay must verify SSH server identity. It must not use
`known_hosts=None`, `StrictHostKeyChecking=no`, or any equivalent host-key
verification bypass for the interactive operator relay.

Host-key trust material is generated or learned as lab-start-owned runtime
state and persisted for the lab identity. The terminal request path consumes a
known-good `known_hosts` file; it does not create trust material lazily while an
operator session is being opened. First-run provisioning may capture a key through TOFU. After pinning, a key mismatch must refuse terminal access.

Keep SSH materials separate:

- the operator client private key lives under the host user's SSH directory and
  remains owned by `src/aptl/core/ssh.py`;
- target `authorized_keys` continue to be public client-key material mounted
  through the existing `./keys` path;
- server host keys and `known_hosts` pins are server identity material and must
  not be stored in, parsed as, or mounted through the client-key/authorized-key
  contract.

Endpoint identity must come from the canonical endpoint boundary. Do not add a
second terminal-only endpoint schema with container names, users, host ports,
or host-key file names. A small terminal projection may combine `ENDPOINT_REGISTRY` with runtime inventory. The registry and deployment backend remain the owners of container, user, and reachability facts.

Generated trust follows ADR-028: ignored state, containment checks, and atomic writes. Failure to materialize a required bind source must stop startup. Persisted private server host keys are operator secrets. Filesystem and archive handling must use restrictive permissions. Public `known_hosts` lines are not secrets, but
they still belong to generated state rather than checked-in config.

Missing pins, key mismatches, invalid known-hosts syntax, and SSH authentication failures use the existing narrow WebSocket error envelope. Logs may name the
container and validation layer, but must not include operator keystrokes,
private key material, or raw secret-bearing exception payloads.

Readiness probes that intentionally trade identity verification for a cheap
"is port 22 accepting key auth" signal are not precedent for the interactive
relay. If those probes are later hardened, they should reuse the same persisted
known-hosts material, but issue #418 is scoped to the operator terminal relay.

## Security Layers

- **WebSocket auth surface:** `terminal_ws` keeps the existing Origin allowlist,
  container allowlist, and lab-running check before dialing SSH.
- **Endpoint identity gate:** reachable host, port, and user data come from the
  canonical endpoint registry/runtime inventory boundary, not from a new local
  map.
- **SSH trust gate:** `asyncssh.connect` receives a concrete persisted
  `known_hosts` path whose entries match the dialed host/port identity. Missing
  or mismatched host keys fail closed.
- **Generated-state containment:** host-key and known-hosts artifacts are
  written only below their owned generated root after path resolution and
  containment checks.
- **Secret classification:** private host keys and the operator client private
  key are control-plane/operator secrets under ADR-029. Public host-key pins are
  not secrets, but they are still generated runtime state.
- **OS/process exposure:** do not pass private key contents, known-hosts
  contents, or trust decisions through shell strings or process argv. Use
  structured Python APIs or `DeploymentBackend` typed methods for any Docker
  interaction.
- **Error envelopes and observability:** WebSocket errors, API responses, logs,
  diagnostics, snapshots, traces, and run archives must not expose private key
  bytes, operator input, or unredacted secret-shaped exception content.

## Extensibility

The extensibility seam is per-SSH-endpoint trust material rooted under one
generated state directory and keyed by the canonical endpoint identity
(`container_name`, SSH user, target host, and target port). Another terminal target should extend canonical endpoint metadata and host-key trust. It should not need a second static endpoint map.

A provider without a local known-hosts path first adapts its endpoint projection. The terminal must still receive one verified SSH identity contract. Do not bypass host
verification because a provider is remote or because containers were rebuilt.

## Non-Goals

- Do not redesign SSH client key generation, target `authorized_keys`, or
  lab-user authentication.
- Do not redesign Docker Compose networking, published ports, or the
  deployment backend protocol beyond the endpoint/trust material needed by the
  relay.
- Do not make the endpoint registry a secret store.
- Do not change intentional vulnerable target credentials or lab realism.
- Do not require operators to manage OpenSSH `~/.ssh/known_hosts` manually for
  the web terminal.
- Do not broaden this issue into a full hardening of every test helper,
  inventory fixture, or readiness probe that currently disables host-key
  checking.

## Anti-Patterns

- Replacing `known_hosts=None` with `known_hosts=[]`, `StrictHostKeyChecking=no`,
  `accept_host_key=True`, or another verification bypass.
- Treating `localhost` or Docker bridge IPs as intrinsically trusted.
- Writing host-key pins during the WebSocket request after the operator has
  initiated an interactive session.
- Storing server host keys beside `authorized_keys` without a distinct contract.
- Duplicating SSH endpoint maps across terminal, snapshot, tests, and Compose.
- Parsing `docker-compose.yml` or shelling out directly from the terminal router
  when `DeploymentBackend` or endpoint registry data already owns the fact.
- Surfacing host-key fingerprints, private key paths with sensitive context, raw
  exceptions, or operator input in WebSocket error messages.

## References

- [ADR-028](adr-028-runtime-rendered-service-config.md): generated runtime
  artifact placement and containment.
- [ADR-029](adr-029-control-plane-secret-handling.md): control-plane secret
  handling boundaries.
- [ADR-036](adr-036-snapshot-endpoint-registry.md): canonical endpoint registry
  and runtime reachability.
- [ADR-037](adr-037-docker-compose-backend-cohesion.md): Docker Compose backend
  cohesion.
- Issue #418: operator terminal relay dials `asyncssh` with `known_hosts=None`.
