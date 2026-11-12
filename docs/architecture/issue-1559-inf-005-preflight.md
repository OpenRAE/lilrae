# Issue #1559: INF-005 certificate generation preflight

Preserve Wazuh's dedicated certificate container and consolidate verification,
not producers or lifecycle policy. Inspection used `f573683d1` on
`1559-go-config-state-keys`. This note adds INF-005-specific guardrails to the
[#1559 configuration and trust preflight](issue-1559-config-state-keys-preflight.md).
It is not an implementation plan or a passed Go design check.
ADR-001, ADR-028, ADR-029, ADR-031, ADR-034, ADR-037, ADR-040, ADR-065,
and ADR-066 already cover the decisions; no new ADR is needed.
Python paths below are relative to `src/aptl/`.

## Production and verification are different owners

`core/certs.py::ensure_ssl_certs` owns Wazuh production through
`generate-indexer-certs.yml`. `config/certs.yml` supplies the legacy identities;
`config/wazuh-certs-tool.sh` is the vendored, digest-checked tool.
`core/helper_images.py` owns helper image digest realization and offline staging
uses those identities. Preserve the fixed generator entrypoint, SAN augmentation,
root aliases, bundle paths, and output formats. Do not replace this producer
with Go certificate issuance or download mutable certificate tooling at startup.

`core/soc_ca.py` owns the separate SOC authority under ADR-034. Its admitted
output/SAN request seam, `derive_soc_service_certs`, remains distinct from the
Wazuh bundle. A single verification owner must cover both shapes without
assuming identical filenames, private-key suffixes, purposes, or reuse policy.
Service-provider integration remains in Go port 19; generic configuration must
not regain Wazuh credential fields or scenario-specific service dispatch.

The verification owner builds on `_soc_ca_chain.py`,
`deployment/_stateful_certificates.py`, `_participant_desktop_tls.py`, and
`backends/_raes_stateful_observation.py`. It owns certificate parsing, key
pairing, signatures, authorities, validity, and name checks using `crypto/x509`.
Production, deployment validation, evidence, and desktop probes consume it.
Standard TLS and SSH transports retain their standard verification mechanisms.
Do not introduce a second verifier inside a producer, probe, or DTO.

## Required cross-cutting passage

| Layer and canonical incumbent | Required passage for INF-005 |
| --- | --- |
| Entry authority: API token/session dependencies, BFF Host/Origin/CSRF checks, terminal gates, MCP common schema/capability checks | Preserve admission before effects. Local CLI startup has operator authority; a scenario declaration or accepted path grants none. No new certificate endpoint, arbitrary command tool, or user-supplied generator UID. |
| Configuration: `core/config.py`, `_credential_sources.py`, ADR-025/065, `internal/canonical` | Keep one non-secret typed config with bounded strict decoding, nested unknown-field rejection, and semantic validation. No certificate-specific config copy or secret values in `aptl.json`. Retain explicit migration and caller-specific discovery rules. Generic strict JSON parsing does not supply typed field validation. |
| Environment: `core/env.py`, `utils/placeholders.py`, `deployment/_environment_bindings.py`, `_compose_environment.py`, `_realization_primitives.py` | Preserve authored/generated/granted/adapter-supplied sources and exact pack/consumer/variable grants. Compose parser interpolation must use authorized lookups, not ambient fallback. Preserve sanitized Compose process variables and distinct Docker/Compose env-file refusal rules. Reject invalid output sets before writes. |
| Artifact admission: `deployment/_compose_stateful_{graph,model,realization}.py` | Keep supported profiles, canonical paths, declared outputs, sensitivity, dependency order, selected consumers, read-only mounts, producer-private exclusions, and effective Compose readback. Preserve remote-daemon refusal before generation: local files do not establish remote bind sources. Use upstream RAES/env-packs schemas, not local copies. |
| Files and locks: `utils/pathsafe.py`, `core/credentials.py`, `core/lifecycle_guard.py`; `internal/securefile`, `internal/filelock` | Use the authorized root and opened handles, reject links/special files, preserve private publication and existing Python-compatible lifecycle locking. Do not copy private credential writers. Per-file replacement is not a bundle transaction; partial or mismatched output must not become valid evidence. Keep workspace ownership and native resource receipts distinct from directory ownership. |
| Host/runtime: `core/hostenv.py`, typed deployment boundary, `core/ephemeral_containers.py` | Preserve daemon selection, owner/project scope, helper labels, argv arrays, cwd, bounded output, deadlines, cancellation, and cleanup. Native Linux generation uses the host UID/GID and a precreated bind source. Desktop/VM/Windows/unknown branches must not evaluate POSIX identity calls. Preserve rootless refusal before material generation; no sudo, root helper, or post-generation chown. |
| Secret exposure and packaging: ADR-028/029, `.gitignore`, `_asset_manifest.py`, `hatch_build.py` | Generated keys stay outside source assets, embedding, logs, argv, shell interpolation, URLs, snapshots, and archives. Deliver only selected material to each consumer. Wazuh PEM files intentionally use `0644` inside `0700` ancestors for non-root bind readers. SOC private keys/passwords use `0600`; public certs and container-readable keystores use `0644` in private directories. Windows confidentiality needs ACLs, not chmod alone. |
| Error envelopes and observability: `CertResult`, `LabResult`, startup diagnostics, CLI/API schemas, MCP `isError`, shared redaction, `LocalRunStore` | Preserve outcomes and entry-layer translation. Return wrapped errors internally; expose safe phases/categories, not raw Docker, parser, x509, OS, or SSH causes. Explicit `slog` goes to stderr. Reuse the redaction parity corpus at every output and persistence boundary; bounded stderr can still contain secrets. Add no certificate exception tree or parallel result schema. |

## Compatibility hazards to settle before code

- **Gate timing differs.** `ensure_ssl_certs` accepts an existing root file
  without cryptographic validation. `certificate_bundle_failure` checks
  declared outputs, then performs full pre-start validation only for file-based
  provenance. Profile-based Wazuh bundles receive cryptographic checks in
  `_raes_stateful_observation`. Do not claim every entry path already validates
  before mutation. Record how consolidation preserves gate timing and public
  errors; functional gaps require the separate bug disposition of #1559.
- **Historical ownership guidance conflicts with current behavior.** The
  [#677 preflight](issue-677-cert-producer-ownership-preflight.md) forbids silent
  rotation of foreign-owned historical bundles. Current `_reclaim_certs_dir`
  instead moves them aside and regenerates, with explicit tests. Record the
  compatibility decision and trust consequences. Neither silently copying the
  behavior nor silently following old prose resolves this conflict.
- **Verification purpose must be explicit.** Use explicit root pools and
  current time, required identities, and appropriate usages. Go's default
  usage is server authentication; do not apply it accidentally to admin/client
  certificates. Bundle provenance checks and endpoint hostname authentication
  differ. Preserve DNS/IP SAN distinctions, Wazuh admin CN rules, root aliases,
  SOC required-name coverage, and the desktop probe's exact issued-leaf check.
  Compare Python acceptance/rejection cases before selecting options. See
  [VerifyOptions](https://pkg.go.dev/crypto/x509#VerifyOptions) and
  [VerifyHostname](https://pkg.go.dev/crypto/x509#Certificate.VerifyHostname).
- **Validity is not renewal eligibility.** SOC reuse has a 30-day margin;
  Wazuh validation checks current validity. Keep these caller policies separate.
  Preserve key/certificate pairing and keystore/password/leaf consistency.
  PKCS#12 support needs a maintained compatible dependency and explicit model
  permission; do not omit formats or write custom cryptography.
- **Startup trust is not session trust.** `core/host_keys.py` captures and
  rewrites pins at startup. ADR-040 requires terminal connections to reject
  missing/unknown/changed pins. Record retained-pin behavior across starts;
  never make the SSH dial path learn or replace trust lazily.
- **Compose parsing changes interpretation.** The handwritten Python parser
  does not implement Compose interpolation. Characterize quotes, comments,
  escapes, duplicates, unset/empty values, and precedence before replacement.
  Interpolation is a source read and must not acquire ungranted secrets. The
  [Compose parser lookup API](https://pkg.go.dev/github.com/compose-spec/compose-go/v2/dotenv#ParseWithLookup)
  is a mechanism, not an authorization policy.

Preserve the isolated generator project-name scheme and its vectors, the
300-second generation budget, the 60-second cleanup budget, and unconditional
`down --remove-orphans` after an attempt. Cleanup failure blocks success.
The leftover generator bridge can overlap lab networks. Reuse the backend
runner seam; do not add another Docker runner or copy image pins into code.

Certificate-file readiness is separate from Wazuh API-listener TLS on port
55000 and authenticated manager readiness. Preserve the phase and sole-retry
owners in [#1002](issue-1002-wazuh-api-tls-warmup-preflight.md),
[#1188](issue-1188-wazuh-api-cold-boot-preflight.md),
[#1191](issue-1191-wazuh-api-cold-boot-rca-preflight.md), and
[#1424](issue-1424-runtime-retry-ownership-design.md).
Do not regenerate certificates to treat an unexplained handshake failure.
Wazuh's narrow insecure-client allowance does not extend to SOC, desktop,
or SSH trust. An open port, repair exit, or generated file is not readiness.

## Extension seams and delivery limits

The next service or hostname belongs in admitted output/SAN requests and the
existing producer profile contract, not another CA or edits to every client.
Verification purpose and time are explicit parameters. Runtime identity
selection belongs in host/runtime classification; execution stays injected
through the typed deployment boundary. Keep renewal, retry, and authority
decisions outside foundation mechanisms.

Use existing certificate, SOC CA, stateful realization, desktop TLS, hostenv,
SSH/host-key, lifecycle, config/environment, redaction, asset, and packaging
tests as the contract inventory. Add conformance cases/vectors before Go and
run them against Python first. Include mismatched keys/roots/SANs, partial
bundles, renewal boundaries, private modes/ACLs, refusal before effects,
unknown/changed host keys, cleanup failure, and cancellation. Real native
Linux/Desktop and supported OS evidence supplements fakes. Random keys need
relationship assertions, not random-byte goldens.

`architecture/model.yaml` owns package/dependency permission; this preflight
does not add speculative packages. The delivery design must declare actual
packages, components, dependencies, and model changes, then pass the existing
design check against `origin/go-cutover`. `internal/process` from #1607 is
absent at inspection: honor #1557 rather than making another runner.
Reuse `.ground-control.yaml`, `.gc/plan-rules.md`, pack-ownership checks,
module pins, generated diagrams, `.golangci.yml`, existing CI selection,
`go-gates.sh`, and mutation thresholds. Local checks stay targeted; full
architecture, mutation, and installed-lab qualification belong to CI.
Keep Python traceability links and add Go links during implementation.

Non-goals are implementation, a delivery sequence, config commands, scenario
acquisition, service-provider credentials, functional repairs, rotation
redesign, external PKI/ACME, remote artifact transfer, new schemas/error
hierarchies/workflow engines, and changes to Python, distribution, public
contracts, resource names, or TLS exceptions. The delivery PR targets
`go-cutover`; passing this review does not certify an implementation design.
