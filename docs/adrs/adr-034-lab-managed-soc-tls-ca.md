# ADR-034: Lab-Managed CA for Verified SOC Stack TLS

## Status

accepted

## Date

2026-05-18

## Reader boundary

This Explanation records design reasons and constraints.
Dated examples, versions, estimates, and measurements describe their stated revision.
They do not establish current interface support or installed qualification.
The [Wazuh Reference](../components/wazuh-siem.md) describes maintained use.
The record's status and amendments still determine its decision scope.

## Context

SEC-006 requires MISP, TheHive, Cortex, and Shuffle to serve certificates
issued by a lab-managed CA, and requires every SOC-stack client to verify TLS
by default. The clients span Python daemons, Python collectors, and TypeScript
MCP servers. The current gap exists because each SOC tool either self-signs at
runtime or serves plain HTTP, so consumers have normalized `verify_ssl=false`,
`curl -k`, and `rejectUnauthorized: false`.

The repo already has relevant owners that must stay canonical:

- `src/aptl/core/certs.py` owns startup certificate generation for Wazuh.
- `src/aptl/core/lab.py` owns lab-start ordering through `_LAB_START_STEPS`,
  `LabResult`, and redacted `StartupDiagnostic` output.
- `src/aptl/core/credentials.py` and ADR-028 own generated artifact placement,
  path containment, atomic writes, permissions, and the rule that checked-in
  `config/` files are source-owned.
- `src/aptl/core/env.py` owns `.env` parsing and placeholder rejection.
- `src/aptl/core/config.py` and ADR-025 own strict first-party durable config.
- `src/aptl/utils/curl_safe.py` owns Python curl transport safety, including
  API-token/header handling outside process argv and `--cacert` support.
- `src/aptl/services/misp_suricata_sync/config.py` owns the strict
  boolean-env parser pattern for service daemons.
- `mcp/aptl-mcp-common/src/http.ts` owns MCP HTTP transport, auth headers,
  timeout handling, and the existing per-request insecure-agent carve-out.
- `mcp/aptl-mcp-common/src/config.ts` owns MCP `docker-lab-config.json` shape
  loading and environment substitution.
- ADR-029 owns the control-plane secret boundary for API keys, private TLS
  keys, generated config, logs, traces, run archives, and MCP telemetry.

## Decision

SOC TLS trust must be implemented as one lab CA contract, not as per-tool
certificate exceptions or per-client trust workarounds.

The SOC CA, public CA bundle, server certificates, and server private keys are
generated runtime artifacts. They must be produced during `aptl lab start`
before bind-mount validation and container startup, using the existing
`core.certs` / `core.lab` orchestration shape. CA and server private keys must remain outside commits, archives, logs, output, MCP configuration, and CLI/API results. Public certificates
may be mounted read-only where needed.

Certificate generation must be parameterized by a small service certificate
registry: service name, output filenames, key/cert permissions, and SANs. The
SAN list is the extensibility seam. Another SOC HTTPS service should register a subject and SAN set with the existing generator. It should not add another CA or ad hoc Compose generator.

SANs must cover both in-network Docker DNS names and host-facing names used by
clients. For example, MISP needs `misp` for containers such as
`aptl-misp-suricata-sync`, and `localhost` / `127.0.0.1` if host-run MCP
servers or collectors connect through the published port. Do not rely on
`--resolve`, disabling hostname validation, or URL rewrites that hide a
certificate/name mismatch.

Python consumers must continue to use `curl_safe.curl_json`. Verification-on
means `insecure=False` and a CA bundle path passed through `ca_cert_path` when
system trust is insufficient. Do not add raw `subprocess.run(["curl", ...])`
call sites for SOC APIs.

MCP consumers must be fixed once in `aptl-mcp-common` HTTP transport and config
shape. Add the CA-bundle option to the common `LabConfig['api']` and per-query
API config surface, then have `HTTPClient` load and apply that CA per request.
Do not solve this by setting process-global `NODE_TLS_REJECT_UNAUTHORIZED`,
`NODE_EXTRA_CA_CERTS`, or by duplicating HTTPS code in individual MCP servers.
The per-query temporary `HTTPClient` path must preserve the same CA and
verification semantics as the default client.

SEC-004's `rejectUnauthorized: false` allowance remains Wazuh-specific. It must
not be copied into MISP, TheHive, Cortex, or Shuffle clients once SEC-006 is
active.

## Security Layers

- **Environment binding:** Values read from `.env` must use `load_dotenv`,
  `env_vars_from_dict`, and `find_placeholder_env_values` where they affect
  startup. Service-local env parsing must follow the strict parser pattern in
  `misp_suricata_sync.config`; typo values like `ture` must fail closed.
- **First-party config shape:** Durable, repo-owned knobs belong in
  `AptlConfig` with `extra="forbid"` or in the existing MCP `LabConfig` shape.
  Do not introduce pass-through dictionaries or duplicate per-MCP schemas.
- **Generated artifact containment:** The generator owns canonical project-relative certificate paths. ADR-028 containment and symlink checks apply before file access, permission changes, and bind-mount references.
- **Secret at rest:** CA private key and server private keys are
  control-plane/operator secrets under ADR-029. Store them only in ignored
  generated state with restrictive permissions; mount private keys only into
  the server containers that require them.
- **OS/process exposure:** API tokens keep using `curl_safe` header temp files.
  Process arguments, healthcheck strings, MCP output, and command errors must exclude private keys, API credentials, and authentication headers.
- **TLS policy gate:** Python clients pass through `curl_safe`'s
  `insecure`/`ca_cert_path` decision. TypeScript clients pass through
  `HTTPClient`'s `verify_ssl`/CA decision. The allowed insecure override is an
  explicit per-client local-debug flag, defaulting to verification enabled.
- **Error envelopes and observability:** Failures should name the layer
  (`soc_cert_generation`, `bind_mount`, `mcp_http_ca`, etc.) and affected
  service, but not PEM content, key paths containing secret names, API tokens,
  or raw upstream bodies. `LabResult`, `StartupDiagnostic`, MCP traces, and
  runstore/export paths continue to rely on ADR-029 redaction boundaries.

## Guardrails

- Keep certificate generation in `core.certs`; extend the existing result
  pattern instead of adding another startup script called directly from the
  CLI.
- Keep lab-start orchestration as a flat `_step_*` sequence in `core.lab`.
  Generated bind-mount sources must exist before `_step_check_bind_mounts`.
- Preserve the existing SSH remote-backend caveat from ADR-028: if generated
  artifacts are created on the host running `aptl lab start`, do not silently
  target a remote Docker daemon whose bind mounts cannot see them.
- Mount public CA bundles read-only into client containers. Mount server
  private keys read-only into the corresponding server container only.
- Update service URLs, healthchecks, seed scripts, collectors, MCP configs, and
  docs together when changing a SOC service from HTTP to HTTPS.
- Rebuild and test every dependent MCP after changing `aptl-mcp-common`.

## Gotchas

- Node's `fetch` path cannot simply accept a custom CA bundle. If a custom CA is
  configured, the common HTTP client needs an HTTPS transport path that supplies
  the CA without process-global TLS mutation.
- Per-query MCP calls construct temporary `HTTPClient` instances. Those instances must copy CA settings so predefined queries keep the same verification as generic API calls.
- Host-run clients using `localhost` and container-run clients using Docker DNS
  names exercise different SANs against the same server certificate.
- Shuffle has both user-facing and backend/OpenSearch TLS surfaces. SEC-006 covers SOC clients of Shuffle. Shuffle's internal OpenSearch trust remains separate unless an explicit change brings it under the same CA.
- `docker compose up` directly from a fresh checkout is not the supported
  generation path. `aptl lab start` must remain the entrypoint that materializes
  generated cert artifacts.

## Known Constraints

- **Cortex HTTPS deferred.** Cortex 3.1.8 ships Play 2.8.19 whose
  `play.core.server.ssl.DefaultSSLEngineProvider` fails reflection at
  runtime with `ClassCastException: No constructor with
  (appProvider:play.core.ApplicationProvider) or no-args constructor
  defined!` regardless of keystore format or HTTP/2 toggle. Verified
  during SEC-006 bring-up: the failure mode is intrinsic to the
  Cortex-bundled Play artifact, not the keystore generation pipeline
  (which round-trips cleanly via `tests/test_soc_ca.py::TestKeystore`).
  Cortex therefore remains HTTP-only on the `aptl-security` network
  until either a Cortex 4.x upgrade or a Play SSL-provider fix lands.
  TheHive now consumes Cortex in-network using the deterministic lab
  fixture key provisioned by `scripts/cortex-apikey.sh` and injected
  into TheHive from `config/cortex/thehive-cortex.env`; there is still
  no separate host-facing `mcp-cortex` client. The existing keystore
  under `config/soc_certs/cortex/` stays reserved for a future HTTPS
  cutover, and the lab CA bundle remains mounted into the Cortex
  container for outbound trust. This defers Cortex server-side TLS
  without disabling TLS verification for any host-facing SOC API.

## Host Exposure Amendment

Host-published SOC management surfaces are operator control-plane surfaces, not
deliberately vulnerable victim targets. When a SOC service is published only so
the operator can use the lab locally, its Compose mapping must bind to
`127.0.0.1` by default. This includes services with host-equivalent Docker authority, such as the historical Cortex and Shuffle components. The default also covers other SOC management interfaces unless a requirement explicitly permits remote access.

The host bind address is the exposure-policy seam. A future remote or multi-operator mode can parameterize the deployment boundary. It must not scatter wildcard host publications across Compose, scripts, tests, and documents. Host clients should keep localhost URLs and shared CA/authentication helpers. Loopback publication does not change the Docker-network URLs used between containers.

Loopback binding is a network guardrail, not a substitute for authentication,
TLS verification, generated-secret handling, or least-privilege Docker
orchestration. A scoped Docker socket proxy is a separate shared API-boundary design. Per-service volume changes cannot replace that design and verification.

## Wazuh Verification Amendment

SEC-009 replaces SEC-004 (issue #1767). The lab Wazuh CA of INF-005 signs the
indexer and manager API certificates. Both certificates also name `localhost`
and `127.0.0.1`, because host-run clients use the loopback publications. The
manager API serves the generated manager certificate, not its self-signed
certificate.

`mcp-wazuh`, `mcp-indexer`, `mcp-network`, and the host-side readiness probes
verify TLS against the lab Wazuh CA. `aptl-mcp-common` has no agent that
disables certificate verification, and it refuses a configuration with
`verify_ssl: false`. This amendment supersedes the Wazuh allowance of the
Decision section and the non-goal about local-debug insecure overrides for MCP
clients. The INF-005 chain stays, so the non-goal about that chain still applies.

## Non-Goals

- Do not redesign the Docker Compose deployment model or introduce a second
  deployment backend.
- Do not replace Wazuh's existing INF-005 certificate chain unless explicitly
  required by a separate Wazuh-focused requirement.
- Do not remove the explicit local-debug insecure overrides; make them opt-in
  and narrow. The Wazuh Verification Amendment removes them for MCP clients.
- Do not move SOC API keys or private key material from `.env` / generated
  state into `aptl.json`, MCP JSON config, README snippets, or run artifacts.
- Do not make collector persistence, OTel tracing, or export packaging the
  first place where secrets are sanitized.
- Do not make remote LAN exposure of SOC management ports the default lab
  posture. Remote access needs an explicit deployment-mode decision.
- A loopback-only fix must not also replace Docker socket mounts. Socket-proxy design and validation need explicit issue scope.

## Anti-Patterns

- One CA per SOC tool, one self-signed cert per tool, or one client-side
  fingerprint pin per consumer.
- Adding `rejectUnauthorized: false`, `curl -k`, `NODE_TLS_REJECT_UNAUTHORIZED`,
  or `SHUFFLE_*_SKIPSSL_VERIFY=true` as the durable fix.
- Duplicating strict boolean parsing, CA path validation, HTTP error handling,
  or auth-header construction in each daemon or MCP server.
- Passing API keys, passwords, PEM blocks, or private key paths through argv or
  unredacted exception text.
- Treating Wazuh inter-component TLS allowances as permission to weaken SOC
  stack consumers.
- Treating `9001:9001`, `3443:443`, or similar bare Compose mappings as
  harmless because a UI has login or TLS. Bare host mappings publish on all
  interfaces unless Compose is given a loopback host IP.
- Changing host-side scripts to use container IPs or security-network addresses
  to compensate for loopback publishes. That bypasses the intended operator
  boundary and makes local versus in-container routes harder to reason about.

## References

- SEC-006 / GitHub issue #258—Verified TLS for SOC Stack Clients via
  Lab-Managed CA
- [ADR-003](adr-003-mcp-common-library.md): MCP Common Library
- [ADR-008](adr-008-soc-stack-integration.md): SOC Stack Integration
- [ADR-022](adr-022-misp-driven-suricata-rules.md): MISP sync client TLS hook
- [ADR-025](adr-025-strict-first-party-config-schema.md): Strict first-party
  config schema
- [ADR-028](adr-028-runtime-rendered-service-config.md): Runtime-rendered generated artifacts
- [ADR-029](adr-029-control-plane-secret-handling.md): Secret handling
- [ADR-031](adr-031-lab-orchestration-contract-guards.md): Lab orchestration
  contracts
