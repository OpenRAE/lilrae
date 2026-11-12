# Issue #1559: Wazuh TLS architecture preflight

Port 08 must centralize certificate verification without merging issuance,
client trust, endpoint identity, and readiness into one policy. SEC-004
preserves Wazuh TLS and its explicit client-local verification exception.
It does not authorize insecure defaults for other clients.
Inspection used `f573683d1` on `1559-go-config-state-keys`.

This is guidance, not an implementation plan or a passed design check.
ADR-025, ADR-029, ADR-034, ADR-040, ADR-052, ADR-065, and ADR-066 already
establish the necessary boundaries; no new ADR is needed. ADR-055 remains
proposed; preserve the implemented ownership controls that it describes.
The delivery design must record actual packages, components, imports, and
model changes in `issue-1559-<topic>-design.md` before Go code. Run the
existing `archcheck design` against the base in `.ground-control.yaml`.

## Trust decisions and canonical incumbents

The current assets demonstrate different policies for different Wazuh links:

| Link | Existing contract |
| --- | --- |
| Manager/Filebeat to Indexer | `docker-compose.yml` selects HTTPS, generated certificates, and `FILEBEAT_SSL_VERIFICATION_MODE=full`. `config/wazuh_cluster/wazuh_manager.conf` separately declares the manager's Indexer client and TLS paths. Preserve both consumers. |
| Dashboard to Indexer | `config/wazuh_dashboard/opensearch_dashboards.yml` selects HTTPS, a CA bundle, and `opensearch.ssl.verificationMode: certificate`. Preserve this existing policy; MCP's exception does not weaken every Wazuh consumer. |
| Dashboard to Manager API | `config/wazuh_dashboard/wazuh.yml` selects HTTPS on 55000. The API listener's runtime certificate state is distinct from the generated Indexer bundle. Generated bundle validity alone does not prove this connection's certificate provenance or readiness. |

SEC-004's `https.Agent` language describes the Node implementation. In
`mcp/aptl-mcp-common/src/http.ts`, the insecure agent is module-scoped and
selected explicitly per request; the configured-CA agent is per client.
The invariant is isolated trust selection, not allocating an agent per call.
Go uses the existing `internal/httpclient.Options.TLS`, which clones the
configuration and roots. An explicit Wazuh exception may select its own
insecure client. Never mutate `http.DefaultTransport`, process TLS variables,
system trust, or another client's configuration. Do not port a Node API
literally into Go.

Keep system roots, explicit supplied roots, and explicit insecure exceptions
distinct. Missing, unreadable, malformed, or empty configured roots must not
become system trust or insecure fallback. SOC clients retain ADR-034
verification by default. MCP common `config.ts`, `endpoint-url.ts`, and
`tools/api-handlers.ts` already own CA resolution, same-origin admission,
and temporary query-client propagation. Authentication exchanges require the
same admitted destination and trust policy as ordinary requests.

One application verification boundary must compose `crypto/x509` with explicit
purpose and declared identities. Reuse the contracts currently spread across:

- `src/aptl/core/deployment/_stateful_certificates.py`: self-signed CA,
  manager-root alias, current validity, key pairing, issuer chain, and
  provenance when present. Env-pack provenance can legitimately omit the
  in-tree document; that does not waive cryptographic validation.
- `src/aptl/core/_soc_ca_chain.py`: CA/leaf reuse, required DNS/IP SANs,
  the 30-day renewal margin, and optional PKCS#12/password/leaf consistency.
- `src/aptl/core/_participant_desktop_tls.py`: verified chain and name,
  followed by exact equality with the declared issued leaf. This path reads
  public outputs only and must not gain access to private keys or passwords.

Share cryptographic checks without combining Wazuh's authority and the SOC
lab CA. Producers, deployment observers, and desktop consumers retain their
different policies. Standard TLS transports still verify peers during
handshakes; this is not a forbidden second application verifier. Do not impose
server-auth defaults on every artifact or use a peer-chosen name/certificate
as its own identity authority.

`core/certs.py`, `core/soc_ca.py`, `_soc_ca_{builders,generation,io}.py`, and
deployment `_compose_stateful_realization.py` own the producer contracts.
`generate-indexer-certs.yml` and `config/certs.yml` own legacy Wazuh generation
inputs. Preserve the pinned image/tool digest, augmented dotted/hyphenated
SANs, host-user ownership, isolated generator project, and unconditional
cleanup. Declared pack outputs and authored hosts supply scenario identities.
Do not put Wazuh credentials, service names, or certificate filenames into
generic config, foundation, or a replacement service registry.

## Required passage through cross-cutting layers

```text
authorized operation -> strict config and explicit credential grants
  -> admitted artifact outputs and identities -> contained protected files
  -> shared certificate verification -> client-local transport policy
safe phase/category facts -> existing result, log, trace, and evidence boundaries
```

These are trust boundaries, not a startup sequence or a new controller.

| Layer and canonical incumbent | Required passage |
| --- | --- |
| Entry authority: `src/aptl/api/{deps,session,schemas}.py`, BFF middleware, terminal routing; MCP common `server.ts` | Preserve token/session, Host/Origin/CSRF, terminal target authorization, and closed Ajv argument checks before effects. Config validity, a relative path, and an env name grant no credential or network authority. Add no route, file tool, or command passthrough. |
| Config shapes: `core/config.py`, `_credential_sources.py`, reference `aptl-config.schema.json`, `internal/canonical` | Use bounded strict Go JSON decoding plus the existing semantic constraints, with one typed config model. Reject unknown/duplicate fields, trailing data, invalid encoding, and semantic failures before project changes. Generic strict JSON decoding does not validate config fields. Preserve missing/null/empty/default distinctions; no second TLS config schema per consumer. |
| Env authority and delivery: `core/env.py`, `utils/placeholders.py`, deployment `_environment_bindings.py`, `_realization_primitives.py`, `_compose_environment.py` | Use ADR-065's Compose dotenv parser with explicit lookup inputs. Preserve authored/generated/granted/adapter sources and exact pack/consumer/variable grants. Parsing and interpolation grant no permission to read ambient secrets. Keep strict booleans, placeholders, NUL/UTF-8 checks, and Docker versus Compose representability checks before writes. |
| Artifact admission: `stateful_realization_errors()`, `_compose_artifact_paths.py`, `_compose_stateful_{graph,model,realization}.py` | Preserve dependency order, canonical paths, declared output/consumer selection, `producer_private` exclusion, read-only mounts, and effective Compose readback/exposure checks. A private CA signing key must never become a client mount. Local generation does not authorize a remote daemon whose bind sources cannot see those files. |
| Files and OS protection: `internal/securefile`, ADR-066, `core/credentials.py`, `_soc_ca_io.py`, `core/hostenv.py` | Establish the trusted root before no-follow access; keep retained handles through reads, publication, and mode changes. Recheck reused material. Keep `0700` parents, SOC keys/passwords and `.env` at `0600`, and deliberately bind-readable Wazuh PEMs/selected artifacts at `0644` inside protected parents. Preserve non-root readability without widening all secrets. Windows ACL guarantees require separate platform handling; modes alone do not supply them. Native Linux and Docker Desktop ownership policies remain distinct. No host-source chown, root repair, or silent escalation. |
| HTTP and process exposure: `internal/httpclient`, `utils/curl_safe.py`, `DeploymentBackend` and existing runner seams | HTTP receives resolved roots and admitted destinations; it does not discover projects or generate certificates. Keep explicit proxy/redirect policy, deadlines, body bounds, cancellation, and safe outcomes. Secrets stay in memory or existing private-file/stdin channels, outside argv, shell strings, healthchecks, and environment dumps. Add no second HTTP, curl, Docker, or generic command runner. Management host publications remain loopback. |
| SSH identity: `core/{ssh,host_keys,endpoints}.py`, ADR-040 | Use `golang.org/x/crypto/ssh` and existing OpenSSH formats with exact host/port pins. Unknown/changed pins fail during sessions. Provisioning bootstrap is separate from ordinary connection/restart. Operator client keys, pivot keys, server host keys, and `authorized_keys` remain distinct. Wazuh's TLS exception grants no SSH verification bypass. |
| Errors and observability: `CertResult`, `LabResult`, startup/deployment diagnostics, CLI exits, API schemas, terminal errors, MCP `isError` | Preserve current projections and safe phase/category failures. Reuse the port 07 redactor and `tests/fixtures/redaction_parity_corpus.json`; inject `slog` to stderr under ADR-065. A logger alone does not redact. Discard sensitive parser/crypto/OS/network text before exposing errors: wrapping, unwrapping, formatting, JSON, spans, and test failures must not leak keys, paths with sensitive context, headers, tokens, or raw upstream bodies. Add an error type only when a caller branches on it. |
| Persistence and workflow: `core/lifecycle_guard.py`, `_compose_resource_ownership.py`, `core/lilrae_config_migration.py`, `LocalRunStore` | Reuse `internal/filelock` and existing project/receipt identities. Names and labels discover resources; verified receipts authorize effects. Preserve lock scope, migration's exact-byte backup/conflict/no-op rules, and canonical identifiers. Per-file atomic replacement is not a multi-file bundle transaction. Revalidate after interruption; cleanup owns only admitted resources. Evidence retains existing public-root fingerprint/validation facts, never private material or credential hashes. |

## Hazards requiring an explicit delivery disposition

- `ensure_soc_certs()` can return from its consistency fast path before
  `_generate_all()` reapplies modes. Consistency checks also use ordinary
  file paths. Wazuh's legacy reuse path checks presence, while typed realization
  performs stronger validation. Do not copy these shortcuts as security policy.
- `certs.py:_reclaim_certs_dir()` renames foreign-owned material and forces
  regeneration, unlike #677's earlier no-silent-rotation guidance. Its hidden
  sibling is outside the exact Wazuh Git/asset exclusions. Synthetic
  `git check-ignore` confirms a sibling `*-key.pem` is not ignored. Recovery
  must preserve trust and secret exclusion; do not copy this behavior blindly.
- Python `load_config()` uses ordinary `json.loads`; Compose dotenv parsing
  also differs from the current handwritten parser. Record intentional
  strictness changes and lookup precedence explicitly. Preserve unrelated
  dotenv lines. Do not weaken Go policy or alter Python to fake parity.
- `internal/securefile` does not enforce Windows private ACLs. Compose it
  with the existing SSH owner's ACL guarantee and real Windows evidence.
  `host_keys.py` also rewrites captured pins during startup; that does not
  enforce ADR-040's rejection of an already pinned changed identity.
- PKCS#12 remains a declared-output contract. `crypto/x509` alone is not
  its encoder/decoder. Record a maintained dependency and architecture
  permission if needed; no custom cryptography, silent format omission,
  retired-service restoration, or new openssl subprocess.
- The inspected model has no `internal/process` or shared Go redactor yet.
  Use their owning ports' contracts rather than competing copies. Missing
  RAES/env-packs Go semantics block consumers; do not implement them locally.

Functional gaps need separate bug tracking outside this milestone under
#1559's rules. Security-policy conflicts need an explicit contract/ADR
disposition before affected code. This preflight changes none of these
runtime behaviors and does not claim complete SEC-004 runtime qualification.

## Extension seam, evidence, and boundaries

The seam is the existing certificate request and declared consumer selection:
expected roots, identities/SANs, purpose, verification time, renewal policy,
format, and final file protection. Additional services or future verified
Wazuh clients change those inputs, not a shared insecure default or another
verifier. Keep current validity separate from renewal eligibility.

Certificate files do not prove listener readiness. Preserve `WazuhApiProbe`,
`_compose_stateful_readiness.py`, and the #1002, #1188, #1191, and #1424
preflights. Transport response, authentication, token shape, manager readiness,
and retry ownership remain separate. Neither an open socket nor HTTP 401
proves authenticated readiness; TLS negotiation failure does not prove a
certificate rejection or a credential fault.

Reuse certificate, SOC CA, desktop TLS, SSH/host-key, lifecycle, stateful
realization, environment-binding, ownership, and common MCP HTTP/CA/security
tests. Extend `docs/reference/conformance-inventory.md` and its existing cases
and vectors only for missing contracts. Applicable conformance cases run on
Python before Go; regression tests separately fail on the base revision.
Evidence must include wrong/expired roots, SAN/key/alias mismatch, corrupt or
stale keystores, renewal boundaries, interrupted bundles, unsafe links/modes,
trust isolation, changed/unknown SSH pins, denied grants, and secret-safe errors.
Use synthetic secrets, temporary keys, real local TLS/SSH peers, and native
Windows ACL/lock checks; mocks or cross-compilation alone do not prove them.

Canonical gates remain `.ground-control.yaml`, `.gc/plan-rules.md`,
`.gc/pack-ownership.json`, `architecture/model.yaml`, `tools/check_pack_boundary.py`,
`tools/cmd/archcheck`, `tools/run-targeted-tests.sh`, `.pre-commit-config.yaml`,
`tools/ci/{select_checks.py,go-gates.sh}`, and `.github/workflows/checks.yml`.
`.gitignore`, `src/aptl/_asset_manifest.py`, and `hatch_build.py` must exclude
generated and recovery secrets. Run targeted local checks and staged hygiene;
CI owns full architecture, mutation, security, and installed-lab qualification.

Non-goals are implementation, an implementation plan, Python/MCP migration,
config commands, service credentials, scenario semantics, TLS-policy upgrades,
new rotation features, SSH TOFU during requests, a common Wazuh/SOC CA, and
new schemas, persistence, redaction, or retry frameworks. Preserve external
files, names, digests, commands, and error contracts. Port 08 supplies shared
configuration/state/key behavior; port 19 owns service-specific integration.
The delivery targets `go-cutover`, without user-documentation or distribution
changes. This note establishes no implementation or verification traceability.
