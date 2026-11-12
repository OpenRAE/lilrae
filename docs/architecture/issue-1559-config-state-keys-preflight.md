# Issue #1559: Configuration, project state, and key material preflight

This note constrains Go port 08, with SEC-006 as its trust contract.
The inspected source revision is `f573683d1`. It records boundaries and
acceptance hazards, not an implementation plan or an approved package design.
No runtime behavior changes in this preflight.

## Decisions and dependency boundaries

Keep durable configuration, project identity, credential authority, certificate
policy, and filesystem protection distinct. A project path locates state;
it does not authorize reading credentials or operating Docker resources.
A certificate fingerprint proves neither resource ownership nor publisher trust.
ADR-055 remains proposed; preserve implemented ownership gates without claiming
that the port implements every proposal in that record.
Configuration and request shape checks finish before project creation,
lock-file creation, hydration, or certificate writes.

```text
authenticated entry -> config and authority gates -> admitted operation
explicit certificate request -> shared verification -> contained state
explicit public trust -> bounded TLS transport -> safe result projection
```

Reuse the foundation already present: `internal/canonical`, `securefile`,
`filelock`, `clock`, `wait`, and `httpclient`. Foundation receives explicit
values and trusted roots; it does not discover projects, hydrate credentials,
select scenario services, or decide certificate renewal. Small interfaces
belong to consumers, with concrete wiring at entry. Do not recreate a generic
core, repository framework, effects container, or exported private helpers.

One certificate boundary owns parsing and cryptographic checks using
`crypto/x509`. It must cover the contracts currently spread across
`core/_soc_ca_chain.py`, `deployment/_stateful_certificates.py`, and
`core/_participant_desktop_tls.py`. Keep their policies explicit: Wazuh root
aliases and provenance, SOC required SANs and keystore consistency, and the
desktop probe's exact issued-leaf comparison. Standard TLS handshakes remain
in `crypto/tls` through `internal/httpclient`. Shared verification does not
require replacing Wazuh's generator, merging authorities, or introducing custom
TLS callbacks. Issue #1570 owns product-specific integration.

Preserve one SOC authority across MISP and Shuffle. Wazuh INF-005 trust and
SEC-004 exceptions remain separate. ADR-063 removed TheHive and Cortex;
historical references in ADR-034 do not authorize restoring them. Preserve a
requested keystore format without creating a retired service to consume it.

## Required passage through cross-cutting layers

Paths below are relative to `src/aptl/` unless another root is named.
These are obligations for the later design, not claims of completed Go support.

| Layer and canonical incumbent | Required passage |
| --- | --- |
| Entry authority: `api/deps.py`, `api/session.py`, `api/middleware/bff.py`, `api/routers/terminal.py`; MCP common config/server and argument-schema gates | Retain token/session, Host/Origin/CSRF, one-use terminal ticket, container allowlist, and lab-running checks before effects. Project selection stays server-owned. No new listener, key download endpoint, request-selected filesystem root, or generic SSH command passthrough. TLS trust does not authenticate an operator. |
| Durable config: `core/config.py:AptlConfig`, `load_config`, `find_config`; `docs/reference/schemas/aptl-config.schema.json` | One typed model retains fields, defaults, discovery rules, optional/null distinctions, path anchoring, and semantic constraints. ADR-065 requires bounded `encoding/json/v2` decoding with exact names, duplicate/unknown-field, UTF-8, non-finite, and trailing-data rejection. `canonical.DecodeStrict` already owns generic strict JSON syntax; it does not validate a config schema. Reuse that responsibility without another generic parser or pass-through map. Keep runtime secrets outside `aptl.json`. |
| Explicit migration: `core/lilrae_config_migration.py`, `docs/reference/configuration-migration.md` | Conversion validates before replacement, holds the lifecycle lock, preserves exact original bytes in `aptl.json.bak`, rejects conflicting backups/concurrent edits, and is idempotent. Loading, doctor, API access, and startup never migrate implicitly. Historical topology conversion must not invent a default scenario or enable retired profiles. CLI commands belong to #1561. |
| Environment authority: `core/env.py`, `utils/placeholders.py`, `core/_credential_sources.py:EnvironmentGrant`, `backends/_scenario_environment.py`, `deployment/_environment_bindings.py` | Keep authored, generated, granted, and adapter-supplied sources distinct. Resolve an exact pack/consumer/variable grant before reading a selected secret. Environment membership, matching names, or parsed `.env` contents alone grant nothing. Preserve placeholder checks, name/uniqueness rules, locator digests, source precedence, and refusal of Docker transport injection. Move Wazuh credential fields to service ownership in #1570. |
| Environment representation: `deployment/_realization_primitives.py:environment_file_line`, `_compose_environment.py` | Use the Compose parser from `github.com/compose-spec/compose-go/v2` for the shared input, with an explicit lookup source. Do not allow default interpolation to read ambient secrets. Parsing does not replace admission or output representability checks. Preserve exact values, single-line Docker delivery, Compose quoting, private files, declared-output joins, and readback. A pack-local `.env` is not an operator source. |
| Files and OS: `utils/pathsafe.py`, `core/credentials.py`, `core/ssh.py`; Go `internal/securefile`, ADR-066 | Supply an owner-selected root; reject unsafe names before normalization and links/special files before access. Use opened handles through reads, writes, permission changes, and publication. Preserve project-relative output locations, atomic visibility, durability, cleanup, and owner protection from the first secret byte. Windows needs the existing private-key ACL guarantee, not just `chmod`. Raw filesystem errors contain paths and require safe projection. |
| Lock and runtime ownership: `core/lifecycle_guard.py`, `deployment/_compose_resource_ownership.py`, `runtime_authority.py`; Go `internal/filelock` | Preserve `.aptl/lifecycle/.lock`, lock-family interoperability with Python, mutation/observation modes, nonblocking busy results, reentrancy ownership, and release on process death. Never replace a held lock inode. Workspace IDs, receipts, native IDs, and grants authorize resource operations; names do not. #1560 owns Docker resources and their receipts. |
| Generated artifacts: `core/lab.py`, `deployment/_compose_stateful_{graph,model,realization}.py`, `_misp_server_tls.py` | Validate admitted output paths, dependency order, sensitivity, consumer selection, read-only mounts, and producer-private exclusions. Generate before bind checks against the effective admitted model. Keep remote Docker's local-artifact refusal. Service-native filenames are delivery projections, not another CA producer. Preserve host-user ownership without root repair, `sudo`, or `chown`. |
| Client trust: `core/collectors.py`, `services/misp_suricata_sync/{config,misp_client}.py`, `utils/curl_safe.py`; MCP common `src/{config,http}.ts` and `tools/api-handlers.ts`; Go `internal/httpclient` | Verification defaults on. Preserve strict per-client debug booleans and existing CA resolution: explicit path, `APTL_LAB_CA_PATH`, `APTL_PROJECT_DIR`, then project-relative fallback for collectors. MCP relative CA paths remain relative to their config, including per-query clients. A configured bad/missing CA fails closed; no fallback to system trust, HTTP, or insecure TLS. Keep explicit lab roots versus system trust separate. Preserve redirect, proxy, timeout, response-bound, and classified-outcome rules; add no retry here. |
| SSH identity: `core/ssh.py`, `core/host_keys.py`, `core/endpoints.py`, `api/routers/terminal.py`, ADR-040 | Use `golang.org/x/crypto/ssh` with the existing OpenSSH key and `known_hosts` contracts. Missing/unknown/changed pins fail closed during sessions. Provisioning alone may bootstrap trust; connecting must not repin. Operator client keys, target `authorized_keys`, pivot keys, and server host identities stay distinct. Use canonical endpoint host/port identity, including bracketed nondefault ports. |
| Errors, logs, and persistence: `CertResult`, `LabResult`, `StartupDiagnostic`, `deployment/errors.py`, CLI/API schemas; `utils/{logging,redaction}.py`, MCP redaction/telemetry; `LocalRunStore` | Retain safe phase/category results and existing presentation envelopes. Use `errors.Is`/`As`; add a category only when a caller branches on it. Do not wrap secret-bearing parser, crypto, URL, process, or response errors verbatim. Inject `slog`, write logs to stderr, and reuse the Go port 07 redactor. Secrets stay outside argv, default object formatting, snapshots, traces, run archives, and exports. Normalize safe metadata before redaction; packaging is not the first scrubber. |

## Contract hazards and extension seams

**Parser compatibility.** #1559 requires the Compose parser; #1513 requires
the same results for supported inputs. Characterize quoting, comments,
interpolation, unset/empty values, duplicates, exports, CRLF, and precedence
against Python and Compose before accepting the replacement. Do not silently
change a supported value or add a second handwritten parser. A difference
needs an explicit contract disposition; a functional gap belongs outside this
port. Input parsing and generated env-file serialization remain separate.

**Certificate lifecycle.** Current SOC artifacts use `config/soc_certs/`,
`lab-ca.{key,pem}`, and service `server.{key,pem}`. Preserve RSA key sizes,
PKCS#8 PEM, SAN DNS/IP types, server-auth usage, ten-year CA/five-year leaf
validity, and the 30-day renewal margin. Reuse requires matching key pairs,
the expected issuer and required names. Leaf replacement invalidates stale
keystores; current keystore reuse requires successful password decoding and a
matching leaf fingerprint. Do not silently strengthen that contract during
the port. Presence or a successful signature alone is insufficient.
Current validity and renewal eligibility are different answers.

Per-file atomic replacement does not make an entire bundle atomic. Keep the
lifecycle lock across validation and publication, detect partial/mismatched
state, and never report it as reusable. Clients must use a coherent trust
snapshot; cached transports must not silently retain a replaced authority.
Do not add overlapping-CA rotation, a new journal, or hot reload in this port.

SOC directories use `0700`; keys and keystore-password files use `0600`;
public certs and encrypted keystores use `0644` for container readability.
An encrypted keystore still carries private material. Wazuh's container-readable
bundle has a different mode contract behind private ancestors. Do not apply
one blanket private-file mode or export the whole cert directory to clients.
Reuse must satisfy protection as well as cryptographic checks.
`securefile.RestrictToOwner` supplies the existing Windows key ACL mechanism;
verify protection at publication rather than adding a chmod-after-write window.
Preserve the operator key under the host user's SSH directory and the public
key distribution paths. Project containment must not relocate that existing
host-owned key or combine it with scenario pivot material.

`x509` path validation can reject material accepted by a handwritten signature
check. Compare renewal/reuse decisions and SAN, issuer, usage, root, and key
checks before choosing options. Do not weaken standard verification to hide
a discrepancy or silently change accepted state. PKCS#12 is a format concern;
use a maintained, permitted dependency if required, not a shell/keytool pipeline
or new cryptographic implementation. Record its component permission and pin.

**Extension parameters.** Certificate requests take admitted output paths,
authored host identities, format, and protection requirements. The next HTTPS
service supplies another request, not another generator or scenario constant.
Issue #875's `derive_soc_service_certs` is the incumbent seam; RAES/env-packs
public types retain SDL semantics. A missing upstream API blocks dependent
scope. Keep the clock and test key-size choices injectable without exposing a
production weak-key setting. Trust roots and debug verification remain scoped
to one client. No process-global trust mutation or cross-project CA cache.

SSH deadlines cover dial, handshake, session I/O, and owned cleanup. Cancellation
must close owned sessions without killing unrelated remote services. This is
not permission to add a generic remote execution facility or change the terminal
frame protocol. Native HTTP carries credentials in memory; any retained process
path uses existing private-file/stdin transports and bounded process machinery.

## Evidence and repository obligations

Use `tests/test_{config,env,env_hydration,credentials,soc_ca,ssh}.py`,
`test_lilrae_config_migration.py`, `test_lifecycle_guard.py`,
`test_compose_environment_bindings.py`, `test_deployment_stateful_realization.py`,
`test_participant_desktop_tls.py`, `test_api_terminal.py`, collector/sync tests,
and MCP common `tests/http-ca.test.ts` as contract evidence. The conformance
inventory already covers config but treats much private state as detail;
that classification does not waive modes, trust, locking, or ownership.
Add missing vectors/cases and run them on Python before Go. Random certificate
bytes are not golden values; assert identities, relationships, protection,
reuse/renewal outcomes, and absence of secrets. Use real TLS, SSH, files, locks,
and native Linux/macOS/Windows evidence; mocks and cross-compiles are insufficient.

Closed-bug searches in this repository on 2026-11-12 identified these lessons:
#186 bounded, noninteractive generation; #951/#984 fresh installed-state
generation before bind checks; #1188 authenticated readiness beyond container
liveness; #1354 safe config failure without traceback; and #1451 closed
credential-bearing result contracts. ADR-029/ADR-040 and their tests retain
the previously recorded secret and host-identity lessons. Open certificate
work includes #1513 and #1570. A focused open `keystore` search found no match;
that does not prove a generic requested format has no future consumer.
Recheck planned uses before removing an incumbent behavior.

Follow `.ground-control.yaml`, `.gc/plan-rules.md`, `.gc/pack-ownership.json`,
`tools/check_pack_boundary.py`, `architecture/model.yaml`, and
`tools/cmd/archcheck`. Before Go, the implementation records each package,
component, dependency, and model change in its `issue-1559-*-design.md` front
matter and passes the design check against `origin/go-cutover`.
This preflight does not replace that record or claim a design-check pass.

Keep `go.mod`/`go.sum`, `.golangci.yml`, the generated architecture diagram,
`tools/run-targeted-tests.sh`, `tools/ci/{go-gates.sh,select_checks.py}`,
`tools/mutation-thresholds.json`, `.github/workflows/checks.yml`, Sonar settings,
and branch protection aligned. Local checks stay targeted, with staged
`pre-commit run`; whole-repository architecture, prose/build, mutation, race,
fuzz, security, and installed-lab qualification use existing CI owners.
Preserve `.gitignore` and `_asset_manifest.py`/`hatch_build.py` exclusions;
later Go embedding must include only tracked assets, never local generated keys.
Keep Python traceability and add Go `IMPLEMENTS`/`TESTS` links during delivery.

## Non-goals and anti-patterns

No implementation, implementation sequence, Python release change, user-doc
change, distribution change, requirement transition, or claim that SEC-006 is
newly delivered. PRs target `go-cutover`; no shipping before Go port 31.
Config commands (#1561), scenario acquisition (#1568), Docker resource ownership
(#1560), and product credentials/providers (#1570) retain their separate owners.

No new configuration file, credential taxonomy, exception family, endpoint
registry, CA service, secret store, authorization engine, or workflow state
machine. Do not move generated secrets into config, embedded assets, MCP JSON,
or run records. No new external processing, hosting, or data transfer.

Avoid one Go package per Python file, private-name compatibility exports,
service-name dispatch in foundation, duplicated validators, presence-only
certificate success, lazy TOFU, process-global insecure TLS, root ownership
repair, and path-check-then-reopen access. Keep explicit local debug overrides;
do not broaden Wazuh exceptions to SOC consumers. Functional gaps require a
separate decision rather than a hidden behavior change during parity work.
