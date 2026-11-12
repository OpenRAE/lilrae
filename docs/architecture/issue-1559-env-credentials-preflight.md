# Issue #1559: Environment Credential Preflight

This INF-006 preflight covers the credential boundary of Go port 08.
The port owns configuration values, project files, credential sources, key
material, and the SSH client. It does not own Wazuh service semantics.
This note constrains the later design; it neither implements INF-006 nor
supplies an implementation plan or a passing design-check record.

No new ADR is needed. ADR-025, ADR-028, ADR-029, ADR-034, ADR-040,
ADR-052, ADR-055, ADR-065, and ADR-066 already establish these boundaries.
The [#1510 preflight](issue-1510-code-quality-preflight.md) remains the
cross-cutting concern inventory.

## Requirement interpretation and compatibility

INF-006 predates the current credential-source and generated-Compose rules.
Its literal wording must not override the following established distinctions:

- The project `.env` holds runtime service values. `aptl.json` holds non-secret
  configuration and source locators, never resolved credentials. Participant
  credentials follow ADR-052; intentional target fixtures follow ADR-029.
  Neither becomes a mandatory project `.env` entry merely because it is a credential.
- Credential synchronization belongs to the admitted lab-start operation, before
  its consumers start. Ordinary CLI invocation, config loading, inspection,
  doctor, and migration do not implicitly hydrate secrets or render service files.
- Checked-in `config/` contains source baselines. Credentialized copies belong
  under ignored generated state, as ADR-028 requires. Never synchronize secrets
  back into tracked templates.
- Static `docker-compose.yml` references runtime operator secrets through
  substitution. Generated Compose uses private files scoped to each consumer,
  as `deployment/_compose_environment.py` requires. Replacing that delivery
  with shared interpolation would undo credential isolation.

The delivery must reconcile INF-006's universal `.env` and substitution clauses
with those contracts in the requirement record. This note identifies the
conflict; it does not change the GRC workflow platform or establish requirement coverage.
Do not silently rewrite designed target credentials to satisfy the old wording.

Two parser changes are explicit in #1559 and ADR-065: Compose-compatible dotenv
reading and strict Go JSON decoding. Python currently parses dotenv line by
line and loads config with ordinary `json.loads`. Record their accepted-input
differences rather than claiming complete parser parity. Cases that pass on
Python remain conformance cases; deliberate Go rejection needs its own stated
contract. Do not change the Python release to make the comparison pass.

## Ownership and existing mechanisms

Python paths below are under `src/aptl/`. They identify behavior owners, not a
module structure to copy into Go.

| Concern | Canonical incumbent and required boundary |
| --- | --- |
| Configuration values | `core/config.py`, `_credential_sources.py`, and `docs/reference/schemas/aptl-config.schema.json` own fields, defaults, discriminated sources, uniqueness, and semantic validation. Keep one Go value definition per contract. File loading is an adapter responsibility; core values do not read files, environment, plugins, or Docker. |
| Discovery and migration | `find_config`, CLI `_common.py`, `core/lilrae_config_migration.py`, and `docs/reference/configuration-migration.md` own discovery, explicit conversion, exact-byte backups, conflicting-backup refusal, concurrent-edit detection, and idempotence. Do not expand search into parents or home, or migrate while loading. |
| Environment syntax and updates | `core/env.py`, `utils/placeholders.py`, and their tests own hydration, preservation of genuine generated values, placeholder rejection, and unrelated-line preservation. Use the dotenv reader from ADR-065's `github.com/compose-spec/compose-go/v2`; do not translate the Python parser or introduce another dotenv library. |
| Source authority and delivery | `_credential_sources.py`, `deployment/_environment_bindings.py`, `_realization_primitives.py`, `_compose_environment.py`, and `backends/_scenario_environment.py` own source selection and transport. Keep authored, generated, granted, and identity-bound adapter values distinct. Syntax parsing grants no authority. |
| Project files and lifecycle | `core/lifecycle_guard.py`, lifecycle policy, workspace ownership, resource receipts, and their individual state owners retain scope and recovery rules. Reuse `internal/securefile` and `internal/filelock`; a project directory is not one universal state DTO or repository. Application code owns lock scope and operation ordering. |
| Certificates and keys | `core/certs.py`, `soc_ca.py`, `_soc_ca_chain.py`, `deployment/_stateful_certificates.py`, `_participant_desktop_tls.py`, `ssh.py`, and `host_keys.py` supply the current invariants. One Go verification owner uses `crypto/x509`; generation, admission policy, filesystem access, and network transport remain separate responsibilities. |
| SSH and endpoints | `core/host_keys.py`, `core/endpoints.py`, terminal routing, and the MCP SSH contracts own trust, endpoint identity, and session behavior. Use `golang.org/x/crypto/ssh`, with small consumer-owned interfaces. The native SSH client does not replace Docker's SSH transport or become a generic host-command service. |
| Shared Go mechanisms | `internal/canonical`, `digest`, `clock`, `wait`, `securefile`, `filelock`, and `httpclient` already exist. Build on their public contracts. Go port 07 owns shared redaction; the process package is assigned to #1607 and is not present at this baseline. Do not create competing fallbacks for unfinished dependencies. |

The actual package names, components, imports, and model changes belong in
`issue-1559-<topic>-design.md` front matter before code. Apply ADR-065's layer
rules and run `go run -C tools ./cmd/archcheck design -base origin/go-cutover <note>`.
This preflight does not enroll speculative packages or amend the model.

## Required security and validation passage

```text
operator-selected project -> strict config + explicit source descriptors
admitted pack + consumer + grant -> selected dotenv/process values
selected values -> placeholder and delivery checks -> private project files
owned startup -> generated-artifact validation -> consumer readiness
errors/results -> safe categories + shared redaction -> existing outward envelopes
```

| Layer | Required passage |
| --- | --- |
| Authentication and authority | Preserve API `deps.py`, session/BFF Host, Origin, CSRF, and terminal allowlists before application calls. No new route, caller-selected server project, or credential lookup endpoint. Scenario text cannot grant host credentials. Keep `APTL_API_TOKEN` and web launch/session credentials distinct from SOC and participant credentials. |
| Config decoding and validation | Use ADR-065's bounded `encoding/json/v2` decoding with exact names, unknown-member, duplicate, invalid-UTF-8, and trailing-data rejection. Preserve missing/null/zero distinctions and existing field validators. `internal/canonical.DecodeStrict` alone does not reject unknown typed fields. Validate deployment host/user/port/key settings consistently, without contacting the backend or exposing raw inputs. |
| Dotenv lookup and interpolation | Supply an explicit lookup context to the Compose parser. Do not inherit its ambient process lookup or default `.env` discovery. Keep project and pack-local `.env` separate; never source a file in a shell or populate the global process environment. Compare effective values and precedence with the Compose execution path, including its filtered client environment. |
| Binding shape and policy | Preserve exact `(pack, consumer, variable)` grant matching, source discriminators, name bounds, duplicate-grant rejection, and declared classifications. A name match is never permission. Generated values require declared producer/consumer joins; adapter values require the admitted pack identity. Keep OPEN versus exact authority checks and denial of Docker transport aliases. Resolve selected process sources once for the admitted operation. |
| Value and transport validation | Preserve placeholder and required-value checks at the owning consumer. Validate NUL, UTF-8, newlines, quote/backslash behavior, and reader-specific limits before publication. Project dotenv, Docker `--env-file`, and Compose `env_file` are different formats. Preserve `environment_file_line` refusal rules; do not trim, double-interpolate, escape differently, or widen transport support silently. |
| Files, persistence, and locking | Use descriptor-relative no-follow access through `securefile`, including reads and chmod. Preserve trusted roots, regular-file checks, private ancestors, create-once versus replacement, final modes, and failure cleanup. Hold the existing lifecycle lock through read/validate/write and migration backup checks; keep its stable inode, reentrancy scope, busy/unavailable distinction, and Python interoperability. No PID-file lock or global lock registry. |
| OS confidentiality | Keep secrets outside argv, URLs, shell text, healthcheck strings, environment dumps, and debug formatting. Use native crypto/SSH APIs and existing private-file or stdin transports. Unix `.env` and private keys use owner-only access. Bind-readable artifacts may require `0644` beneath a verified `0700` directory; preserve that qualified exception instead of blanket `0600`. Windows modes do not create private ACLs: reuse `securefile.RestrictToOwner` where that contract applies. Qualify access at creation, not only after bytes become visible. |
| Certificate trust | Centralize cryptographic verification, with explicit expected roots, identities, usages, current time, and renewal policy. Preserve key pairing, CA constraints, chain validity, DNS/IP SANs, bundle consistency, and keystore/leaf agreement. Reuse the existing clock. Service callers supply purpose-specific policy; they do not duplicate verification or replace it with file existence. Desktop TLS also compares the served leaf to the issued leaf. |
| SSH trust and lifetime | Consume startup-owned pins for the exact dialed host/port; unknown, changed, malformed, or missing pins fail closed. TOFU is confined to provisioning, never an interactive connection. Operator client keys, scenario pivot keys, server host keys, and public authorized keys are different materials. Bound connect, handshake, command, streams, cancellation, and close; settle pending callers and report uncertain remote cleanup rather than claiming termination. |
| Errors, logging, and evidence | Preserve `deployment/errors.py`, `LabResult`, startup diagnostics, CLI exits, API envelopes, and MCP `isError` projections. Go callers use `errors.Is`/`As`; add a category only when callers act on it. Never wrap a secret-bearing parser or SSH error into public text. Use injected `slog` and shared redaction at every outward sink, including traces, snapshots, run writes, and test diagnostics. Logs go to stderr, outside JSON/MCP protocol output; no import-time logging setup. Logging configuration and bounded output are not redaction. |

Unknown environment entries must not be rejected as unknown config fields:
strict first-party configuration and an extensible dotenv key set have different
contracts. Conversely, permissive dotenv syntax does not relax source authority.
Schema validation, delivery representability, artifact validation, and runtime
readiness check different facts; removing repeated checks must not remove a gate.

## Whole-repository constraints and extension seams

Preserve `.aptl/`, `.env`, existing key locations, public names, digest domains,
and the vectors under `conformance/testdata/vectors/`. Do not rename persisted
`APTL_*` interfaces or put resolved credentials or secret-derived hashes into
config/provenance identities. Workspace identity and resource receipts remain
with their lifecycle owners; names alone never authorize resource reuse/deletion.

Wazuh fields leave generic `EnvVars`; Go port 19 owns service credentials,
rendering, and readiness. The seam is a consumer's declared credential needs
and typed resolved bindings, backed by existing source descriptors. Adding a
service must not require editing a global Wazuh-shaped environment bag.
Preserve hydration's no-rotation behavior and authoritative fixture reconciliation
without copying service-specific generation tables into generic core.

Port 19 must retain `credentials.py`'s format-safe YAML/XML substitutions,
missing-marker refusal, and cluster-only key replacement. A generic secret
writer must not learn those formats or edit unrelated TLS key elements.
Atomic replacement protects one file; it does not make a multi-file render
transactional. A partial failure must stop startup before any consumer uses
stale or mixed credentials, without printing the rendered content.

Certificate verification accepts expected trust, usages, identity, and renewal
policy; certificate production retains declared subjects, SANs, outputs, and
consumer modes. Share verification without merging the Wazuh and SOC issuance
workflows, trust roots, or the separately managed manager API listener.
Keystore formats remain consumer contracts, not permission to add unreviewed
crypto dependencies. Endpoint-specific SSH pins reuse canonical endpoint identity.
New credential-source kinds extend the existing discriminated locator contract,
not arbitrary commands, URLs, plugin imports, or provider-specific brokers.

Startup keeps one admitted plan and its existing retry/readiness owners.
Generating files does not prove authenticated service readiness. Preserve the
[#677](issue-677-cert-producer-ownership-preflight.md) producer-ownership rule,
the [#1002](issue-1002-wazuh-api-tls-warmup-preflight.md) transport/auth distinction,
and [#1188](issue-1188-wazuh-api-cold-boot-preflight.md)/
[#1191](issue-1191-wazuh-api-cold-boot-rca-preflight.md) recovery limits.
No root repair helper, automatic trust rotation, nested retry, or volume cleanup
is a credential-management fix. `supports_local_artifacts=False` remains a
refusal for controller-local files with remote Docker bind mounts.

The [#1413 preflight](issue-1413-configured-pack-source-preflight.md) remains
authoritative for pack admission and project/pack separation. RAES and env-packs
own schemas and semantics; unavailable upstream Go contracts block their use.
`.gc/pack-ownership.json` and `tools/check_pack_boundary.py` still apply.

Review every artifact boundary: `.gitignore`, `_asset_manifest.py`,
`hatch_build.py`, installed-asset exclusions, Docker build contexts, runstore,
archives, CLI/API/MCP projections, and telemetry. At baseline `f573683d1`,
the root `.dockerignore` excludes neither `.env` nor generated secret directories.
Git ignore rules do not exclude Docker build context inputs. This is an
exposure risk, not evidence that a build uploaded secrets; any functional repair
belongs to a separate bug issue, outside this port's behavior-preservation scope.

## Evidence and delivery limits

Reuse `tests/test_config.py`, `test_env.py`, `test_env_hydration.py`,
`test_compose_environment_bindings.py`, `test_credentials.py`,
`test_lilrae_config_migration.py`, `test_lifecycle_guard.py`, `test_soc_ca.py`,
`test_certs.py`, `test_ssh.py`, and `test_host_keys.py`, plus their fuzz and
consumer tests. Extract observable invariants, not private mock structure.

Closed-`bug` searches in `OpenRAE/lilrae` supplied these additional lessons:

| Evidence | Invariant to carry into Go tests or conformance |
| --- | --- |
| [#184](https://github.com/OpenRAE/lilrae/issues/184), [#1354](https://github.com/OpenRAE/lilrae/issues/1354) | Consumers use the selected project source; invalid config and deployment settings fail safely before effects, across commands. |
| [#266](https://github.com/OpenRAE/lilrae/issues/266), [#1105](https://github.com/OpenRAE/lilrae/issues/1105) | Paths cannot redirect privileged writes, even through races; argument arrays do not prevent secret disclosure through argv. |
| [#185](https://github.com/OpenRAE/lilrae/issues/185), [#417](https://github.com/OpenRAE/lilrae/issues/417), [#418](https://github.com/OpenRAE/lilrae/issues/418) | Redact before persistence, exclude operator keys from target evidence, and reject untrusted SSH peers. |
| [#186](https://github.com/OpenRAE/lilrae/issues/186), [#189](https://github.com/OpenRAE/lilrae/issues/189), [#1290](https://github.com/OpenRAE/lilrae/issues/1290) | No interactive privilege escalation, stranded callers, leaked timers, or continued output buffering after timeout. Channel closure alone is not proof of remote process death. |
| [#951](https://github.com/OpenRAE/lilrae/issues/951) | Fresh installed projects cannot rely on a developer's ignored certificates or validate mounts from an unused static Compose model. |

Extend the Go port 03 contract inventory before code and run the new conformance
cases on the Python release. Explicitly account for parser differences, quoting,
ambient-source denial, failure-before-write, partial publication, interrupted
migration, key/cert mismatch, renewal, host-key rejection, and Windows ACLs.
Use synthetic values and isolated roots; failure reports must not print them.
One verifier still needs purpose-specific rejection cases, including SAN, trust,
usage, and served-leaf mismatch. Existing security behavior is the floor.

Use `.ground-control.yaml`, `.gc/plan-rules.md`, `architecture/model.yaml`,
`tools/cmd/archcheck`, `tools/run-targeted-tests.sh`, staged `pre-commit run`,
and the existing CI selector, Go gates, Sonar, and branch protections.
Target `go-cutover`. Full architecture checks, mutation, coverage, fuzz campaigns,
and installed-lab/platform qualification remain CI-owned. A documentation
preflight does not satisfy those gates or create `IMPLEMENTS`/`TESTS` coverage.
Delivery adds Go links for the supplied requirement UIDs and retains Python links.

Non-goals: implementing #1559 here; a new secret manager, environment broker,
universal state schema, exception hierarchy, redactor, workflow engine, or
certificate parser; service-specific credentials (port 19), config commands
(port 10), scenario sources (port 17), remote staging, auth redesign, functional
gap repairs, Python release changes, user documentation, distribution changes,
or release before port 31. Do not port unused code without checking planned uses.
