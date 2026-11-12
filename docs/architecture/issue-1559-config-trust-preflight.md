# Issue #1559: Configuration and trust boundaries preflight

This note covers CLI-007 within Go port 08 at revision `f573683d1`.
It records architecture constraints, not an implementation plan or a completed Go design.
The Python command already implements CLI-007.
Port 08 supplies shared loading; port 10 owns the Go `config` commands.
No new ADR is needed: ADR-025, ADR-029, ADR-034, ADR-040, ADR-052, ADR-055, ADR-065, and ADR-066 govern these boundaries.

## Decisions and compatibility

Keep one typed, non-secret configuration model and one defaulting and validation authority for all Go consumers.
Configuration values and predicates belong in core; file loading belongs outside core, using foundation file access.
Entry code owns rendering, exit statuses, and transport-specific error conversion.
Application code owns mutation ordering and lifecycle ownership.
Do not reproduce Python modules, private re-exports, or its import graph as Go packages.

The inspection flow is:

```text
selected project directory -> discovery -> file read -> JSON syntax gate
  -> typed defaults and configuration validation -> resolved configuration
  -> port 10 presentation -> stdout
safe failure category and field location -> entry error conversion -> stderr
```

There is no edge from inspection to credential resolution, migration, pack acquisition, backend construction, or network access.
These boundaries matter even if a convenience project constructor could perform all those operations.
An invalid configuration must fail before project creation, hydration, locks that create files, or other mutation.

- `core/config.py::find_config` checks only `aptl.json` in the supplied directory.
  CLI `_common.resolve_config_for_cli` uses it directly; its comment about walking parents does not describe current behavior.
  Separately, `lifecycle_guard.canonical_lifecycle_project_root` resolves the path and searches ancestors for lifecycle ownership and migration.
  Preserve each caller's discovery contract; do not silently unify these policies.
- Missing configuration is an inspection failure, even though some API and experiment paths permit default-only operation.
  Keep that missing-file decision at the operation boundary, outside the shared decoder.
- Defaults apply to omitted fields, not indiscriminately to explicit nulls or zero values.
  For example, omitted `lab` uses its default, but `lab: {}` fails because its `name` is required.
  Preserve `containers.profiles: null` versus `[]`, nullable sections, list order, strict fields, coercions, and normalized values.
  A Go zero value or `omitempty` is not a substitute for these rules.
- `config show` validates through the loader; `config validate` additionally checks deployment construction settings without contacting the backend.
  Do not add that construction step, startup readiness, certificate checks, or installed-model availability checks to inspection.
  Preserve checks that belong to operation admission separately from pure configuration predicates.
- `config show --json` emits the resolved object with defaults and no result envelope.
  Do not apply `_common.emit_json_result` or reuse the narrower API `ConfigResponse` or provenance projection.
  Keep `--project-dir/-d`, `--json`, success 0, loading failure 1, stderr diagnostics, and empty stdout on failure.
  Invalid command usage remains 2.
- Human output currently follows model field order, renders null as an empty value, and renders booleans as lowercase text.
  Nested values also appear in the tables; avoid Go map iteration and language-dependent value formatting.
  Preserve field coverage and stable ordering through an explicit presentation boundary in port 10.
  JSON whitespace and terminal layout need not become digest or persistence contracts.

## Cross-cutting passage and canonical owners

Python paths below are relative to `src/aptl/`; they identify behavioral owners, not a requested translation structure.

| Layer | Incumbents and required passage |
| --- | --- |
| JSON syntax and configuration shape | `core/config.py`, `_credential_sources.py`, `docs/reference/schemas/aptl-config.schema.json`, ADR-025, and `internal/canonical.DecodeStrict`. Reject unknown members at every first-party level, invalid roots, invalid discriminators, and trailing input. The generic strict decoder does not supply config fields, defaults, or semantic predicates. Use the ADR-065 JSON mechanism and existing syntax rules; do not write another parser. JSON Schema describes structure but neither inserts defaults nor expresses every Python validator. Do not create another authoritative config schema for inspection. |
| Configuration policy | Keep project-name bounds, operator-group token bounds and uniqueness, positive lifecycle durations, UTC schedule normalization, immutable participant model IDs, closed provider selections, and source/root/pack-directory compatibility in the shared model. Preserve current strict versus coercing fields explicitly. Path syntax checks must not trigger pack loading or filesystem acquisition. |
| Credential-source shapes and authority | `_credential_sources.EnvironmentGrant`, `ProcessEnvironmentCredentialSource`, `ProjectEnvironmentFileSource`, ADR-052, and `deployment/_environment_bindings.py`. Keep closed source kinds, bounded variable locators, and unique `(pack, consumer, variable)` grants. Process-source variables use the uppercase pattern; project-file variables permit the existing mixed-case pattern. Inspection returns descriptors, never their resolved values. Runtime binding still checks the exact admitted pack, consumer, classification, generated-output reference, and realization authority. Matching a variable name grants no access. |
| Environment parsing and delivery | `core/env.py`, `utils/placeholders.py`, `deployment/_realization_primitives.environment_file_line`, and the ADR-065 Compose module. Use Compose's dotenv parser rather than a new line parser. Supply an explicit lookup context; never let interpolation introduce ambient credential reads. Input dotenv parsing and output env-file representability remain separate concerns. Preserve Docker versus Compose encoding, NUL/UTF-8 checks, line limits, quoting restrictions, placeholder rejection, and rejection before mutation. Wazuh credential fields and service defaults belong to the port 19 providers, not generic Go config or env models. |
| Filesystem and private persistence | `utils/pathsafe.py`, `core/credentials.py`, `core/lilrae_config_migration.py`, `internal/securefile`, and ADR-066. Reuse contained, descriptor-relative no-follow access for generated state and migration. Validate raw relative paths before cleaning; keep ordinary-file checks and exclusive creation distinct from replacement. Preserve modes, atomic publication, durability, cleanup, backup conflicts, and concurrent-edit refusal. `securefile.OpenDir` trusts its root and can follow root links: the project owner must establish that root. Do not silently apply new generated-state restrictions to authored config discovery. |
| Project ownership and locking | `core/lifecycle_guard.py`, runtime ownership receipts, ADR-055, and `internal/filelock`. Project paths do not establish permission to mutate Docker resources. Preserve receipt and owner-label checks, stable lock files, acquisition scope/order, caller-owned reentrancy, immediate busy failures, and Python/Go mutual exclusion. Windows shared lifecycle observation fails closed; do not emulate it with an exclusive lock. Inspection currently takes no lifecycle lock and must not acquire one merely to share a project abstraction. |
| Migration | `core/lilrae_config_migration.py` owns explicit conversion. Keep the lifecycle lock across validation, exact-byte backup, concurrent-edit check, and atomic replacement. Preserve idempotence, explicit scenario selection, unrelated fields, and retired-profile refusal. Loading and inspection never migrate, repair, or rewrite a file. Port 08 owns migration behavior; port 10 owns its command. |
| Certificate verification | `_soc_ca_chain.py`, `deployment/_stateful_certificates.py`, `_participant_desktop_tls.py`, `core/soc_ca.py`, and ADR-034. Use one verification path built on `crypto/x509`; do not leave competing signature, validity, or hostname checks in consumers. Keep caller policies explicit: admitted root, CA constraints, time, DNS/IP SANs, key usage, certificate/private-key match, required outputs, and desktop's exact issued-leaf comparison. A valid chain alone does not establish all these policies. No process-global trust change, insecure fallback, or regeneration to hide invalid retained material. |
| Certificate production and artifacts | `core/certs.py`, `soc_ca.derive_soc_service_certs`, generated-artifact consumer selection, and the #677 preflight. Keep producer execution identity separate from runtime service identity, public certs separate from private keys, and required outputs/modes separate from service policy. SANs and consumers derive from admitted declarations; do not recreate a service-name registry in generic Go code. Existing Wazuh and SOC generation contracts are distinct from the shared verifier. Preserve CA reuse and partial-material failure behavior. |
| SSH authentication and server identity | `core/ssh.py`, `core/host_keys.py`, `core/endpoints.py`, `api/routers/terminal.py`, deployment `ssh_compose.py`, and MCP common SSH code. Build the client with `golang.org/x/crypto/ssh`; use its maintained known-hosts support for existing pin formats. Client keys, server host keys, `known_hosts`, and target `authorized_keys` have separate purposes. Preserve exact host/port identity, including bracketed nonstandard ports. Unknown or changed keys fail; TOFU is permitted only at the existing provisioning boundary, never during a terminal request. Keep operator keys separate from scenario pivot keys and their evidence classification. |
| Entry authentication and transport shapes | API `deps.py`, BFF/session middleware, terminal Origin/container/running checks, API `schemas.py`, and MCP common `server.ts` remain the entry gates. Shared loading adds no bypass, listener, or raw-config API endpoint. Existing token, Host, Origin, CSRF, and session checks precede protected operations. MCP argument validation precedes effects; preserve its `isError` conversion. The local inspection command relies on local file access, not a new authentication system. |
| OS exposure, errors, and observability | ADR-029, `utils/redaction.py`, MCP common redaction, `utils/logging.py`, deployment errors/results, and ADR-065 entry conversion. Keep secrets out of argv, public formatting, logs, traces, causes, test diffs, and error envelopes. Use memory, existing stdin transport, or private files as appropriate. Return safe operation/category and field locations; never echo input values or raw parser, dotenv, SSH, or backend errors. Use the port 07 shared redactor at output boundaries, not a parallel filter. Add an error type only when a caller branches on it; preserve busy, unavailable, cancellation, and timeout distinctions. Inject `slog` when needed; logs go to stderr, with no library logging setup. |
| Evidence and identity | `core/provenance/providers/config_identity.py::safe_config_projection`, descriptor digest methods, `LocalRunStore`, and the shared serialization vectors. Local inspection output is not an archival DTO or a configuration identity. Provenance excludes paths and locators that inspection can display. Preserve `credential-descriptor-digest` and `ssh-key-fingerprint` vectors and their framing; do not hash rendered tables or substitute a file hash. |

Windows requires particular care.
The current `internal/securefile` mode operations do not establish private ACLs; its documentation says so.
`core/ssh.py::_harden_private_key_windows` provides a separate OpenSSH ACL contract.
Port 08 must retain and qualify that protection through the existing platform boundary, rather than claiming `0600` supplies it.
Keep inherited project ACL behavior where that is the existing contract.
Linux and macOS no-follow checks and Windows reparse checks require real handle-based evidence, not cross-compilation alone.
Keep authored-template containment distinct from generated-output no-follow policy; `credentials._resolve_within_project` permits contained template links.

SSH transport does not make a remote command an argument array.
Retain existing shell formatting, request validation, output bounds, PTY/session behavior, and bounded cancellation and cleanup at the owning consumer.
Do not concatenate config fields into a remote shell command or add an unrestricted command runner.
Retain SSH Compose's `supports_local_artifacts=False`; a native SSH client does not establish remote artifact staging.
Configuration inspection must remain usable without SSH initialization or private-key reads.

## Compatibility risks that must remain visible

The current config reader uses ordinary `json.loads`, unlike `utils/strict_json.py` and the Go strict decoder.
Duplicate-member and non-finite handling can therefore differ between the Python reader and the required Go policy.
Typed decoding can also change coercion, case matching, explicit-null handling, or omission behavior.
Record boundary-specific accepted and rejected inputs and resolve discrepancies explicitly before claiming parity.
Do not weaken strict Go policy or silently change the Python release to make a comparison pass.
The #1555 preflight already records this policy tension.

Compose dotenv parsing also differs from the current hand parser for interpolation, comments, escapes, and multiline values.
Issue #1559 requires the maintained parser, but does not authorize ambient environment forwarding or arbitrary behavior changes.
Qualify its parser options and explicit lookup against both project-file consumers and Compose's effective values.
Record any irreconcilable behavior difference for a separate functional-gap decision; do not hide it in a parser refactor.

`_common._load_config_or_exit` currently prints `str(exc)`.
Top-level `hide_input_in_errors=True` does not make custom validators' interpolated messages safe.
For example, lab-name and provider validators include rejected input in their own text.
Do not copy this error propagation into Go or claim the existing redactor automatically protects it.
Use synthetic secret-bearing invalid input to verify both streams and logging boundaries.
Schema-valid descriptors remain locators; loader success must never dereference their credentials.
Field-location diagnostics must also bound and sanitize untrusted member names; an unknown JSON key can itself contain a secret.

## Extensibility without another framework

The shared loader returns a validated configuration and its owning project location, without choosing a presentation or performing runtime admission.
Callers retain their required-file versus optional-file policy and existing discovery policy.
A future config field enters the same model, defaulting, validation, and contract evidence; inspection must not maintain a competing field list.
Stable presentation ordering belongs at the presentation seam, independently of identity encoders.

Certificate consumers pass their expected identity, purpose, admitted roots, and verification time to the single verification path.
They retain artifact selection and operation policy; avoid a universal verifier with an insecure boolean escape hatch.
Environment consumers supply an explicit lookup and reader-specific delivery choice.
SSH consumers supply endpoint identity, client authentication, trusted pins, and operation context.
Use small consumer-owned effect interfaces, not a generic project service, credential registry, or I/O framework.

## Evidence and workflow boundaries

Reuse `tests/test_config.py`, `tests/test_cli_config.py`, config-migration tests, environment-binding tests, and existing env, credentials, lifecycle, CA, and SSH tests.
The black-box anchors are `conformance/testdata/cases/config.txtar`, `options-config.txtar`, the reference config schema, and `conformance-inventory.md`.
The current config case checks schema acceptance and a text field; it does not prove every default, discovery distinction, or no-effects invariant.
Port 08 needs shared contract vectors for its library behavior; port 10 needs command parity against the same resolved values.
Conformance additions run against the Python release before Go; bug regressions separately fail on the base revision.
Use synthetic material, temporary project roots, real TLS/SSH peers, and native platform checks; retain mutation, race, and fuzz gates.

The #677, #1002, #1188, #1191, and #1413 preflights remain applicable.
Certificate production is not authenticated readiness; transport failure is not an authentication failure or proof of its cause.
Retain one lifecycle retry owner, authenticated readiness, runtime identity, retained volumes, and pack-owned service facts.
This repository inspection does not establish the current status of external bug issues or planned-use issues.
Complete the issue's required searches before dropping apparently unused behavior; do not infer dead code from CLI imports alone.

Delivery must record packages, components, dependencies, and model changes in an ADR-065 design note before Go code.
Run the required scoped `archcheck design` against `origin/go-cutover`; this preflight is not that package design or gate result.
Reuse `architecture/model.yaml`, its generated diagram, root/module manifests, `.golangci.yml`, `.gc/pack-ownership.json`, and `tools/check_pack_boundary.py`.
Keep `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/run-targeted-tests.sh`, staged-file pre-commit, and existing CI routing/gates authoritative.
Whole-repository architecture, full suites, mutation, coverage, and installed-lab qualification remain CI responsibilities.
Retain Python traceability and add Go `IMPLEMENTS` and `TESTS` links during delivery; do not mark CLI-007 complete from a loader-only port.

Non-goals are implementation, a command in port 08, automatic migration, credential hydration during reads, new configuration fields, and new authentication or error frameworks.
Also excluded are scenario/pack semantics, service-specific credentials, readiness redesign, new persistence layouts, user documentation, distribution changes, and Python behavior changes.
Use the released RAES and env-packs Go APIs for their semantics; a missing API is a dependency blocker, not permission to duplicate it.
Target `go-cutover`; nothing ships before port 31.
