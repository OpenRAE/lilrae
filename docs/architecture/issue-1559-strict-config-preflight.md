# Issue #1559: Strict configuration validation preflight

CLI-002 requires configuration rejection before deployment effects.
Inspection used `f573683d1` on `1559-go-config-state-keys`.
This note records validation boundaries, not an implementation plan or a
passed package-design check. ADR-025 and ADR-065 already govern; no new ADR
is needed. The [state and trust preflight](issue-1559-config-state-keys-preflight.md)
covers the issue's certificate, SSH, and private-state contracts.

## Validation authorities

Keep one typed configuration contract, separate from loading and presentation.
Core values and predicates must not import filesystem loaders, scenario
acquisition, deployment implementations, or command frameworks. Application
code coordinates effects; entry code constructs dependencies and maps errors.
Do not reproduce Python's config/scenario/backend import cycle or eager SSH
imports. Existing responsibility owners are behavioral references, not a
module structure to translate.

Three checks protect distinct invariants:

| Check and canonical incumbent | Required boundary |
| --- | --- |
| JSON and config shape: `src/aptl/core/config.py`, `_credential_sources.py`, ADR-025, reference `aptl-config.schema.json` | Bounded input, one object, nested unknown-field rejection, types, defaults, required members, and local cross-field predicates. No credential lookup, pack acquisition, network, or state creation. |
| Deployment settings: `core/deployment/__init__.py:get_backend`, `ssh_compose.py`, CLI `_common.exit_on_invalid_deployment_settings` | Preserve required SSH host/user, port range, host/user syntax, key-path rules, and remote local-artifact refusal. Share pure predicates between validation and construction. Backend initialization or connection is not a substitute for validation. |
| Scenario admission: `backends/raes_profiles.py:select_backend_profiles`, RAES admission, realization validators | Check selected groups against the admitted vocabulary and plan before their effects. Keep capability, grant, output/consumer, and runtime authority checks with their existing owners. Config syntax alone cannot establish realizability. |

`containers.profiles` is a bounded selection from the admitted scenario.
Preserve uniqueness, at most 128 tokens, and the existing token syntax and
128-character bound. Missing or null uses admitted defaults; `[]` selects no
groups. Do not invent a fixed profile enum, compatibility matrix, topology
booleans, or scenario facts in generic config. Scenario selector fields and
source/root/pack-directory exclusions remain in the wire schema, without
acquisition during validation. Port 17 owns scenario semantics.

## Compatibility decisions before code

- `{}` has defaults, but `{"lab": {}}` lacks required `lab.name`. Preserve
  absent, null, zero, false, and empty-list meanings per field. Initializing
  every Go nested struct with defaults would erase required-member failures.
  Preserve current normalization, bounds, literals, provider/model matching,
  lifecycle duration/schedule rules, and credential-source discriminators.
- `find_config` checks only the supplied directory for `aptl.json`.
  `canonical_lifecycle_project_root` separately finds an ancestor project for
  lifecycle locking. Preserve each caller's discovery and missing-file policy.
  Optional-config callers may default when absent, never when a present file
  is invalid. CLI `_common`'s upward-discovery wording is not loader behavior.
- ADR-065 requires exact casing, duplicate-name and invalid-UTF-8 rejection,
  no non-finite numbers, one value, no trailing data, and bounded input. Reuse
  `internal/canonical`'s strict-JSON policy and vectors. `DecodeStrict` neither
  checks config members nor supplies defaults or a byte limit. Typed decoding
  still needs unknown-member rejection and semantic checks. Do not add another
  token parser or convert generic numbers through float64 to populate config.
- Python's loader uses `json.loads`, and some Pydantic fields coerce scalars.
  Characterize those inputs before choosing Go types. Record ADR-065 parser
  differences explicitly and resolve field-coercion conflicts with parity in
  the delivery design. Do not silently tighten every field or weaken Go's
  strict reader. Keep the Python release unchanged.
- Choose and justify the config byte limit before allocation. Contained reads
  are not bounded reads. Do not borrow a pack or MCP limit without evidence.
  Keep numeric range errors distinct from missing/defaulted values.
- Keep `docs/reference/schemas/aptl-config.schema.json` aligned with its config
  owner. It neither inserts defaults nor expresses every semantic validator.
  Do not create another runtime schema, API model, or command-local validator.

## Required passage through shared boundaries

Python paths in this table are relative to `src/aptl/`.
These are obligations for the intended design, not completed Go controls.

| Layer and canonical incumbent | How the intended design satisfies it |
| --- | --- |
| Auth and entry shapes: `api/{main,deps,session}.py`, BFF middleware, terminal router, shared MCP schema gate | No new endpoint or auth mode. Later consumers retain bearer/session, Host/Origin, tool-schema, target eligibility, and server-owned project selection before effects. Config validity grants no operation authority; API DTOs are projections, not another config schema. |
| Secret descriptors: `_credential_sources.py`, ADR-029/052 | Keep closed source kinds, variable bounds, unique exact pack/consumer/variable grants, and locators without values. Participant sources and scenario grants have different consumers. Successful validation must not resolve either. No ambient credential fallback or generic secret bag. |
| Environment: `core/env.py`, `utils/placeholders.py`, `backends/scenario_startup.py`, deployment `_environment_bindings.py` and `_realization_primitives.py` | Preserve authored/generated/granted/adapter source distinctions, exact admitted-consumer authorization, placeholders, source precedence, output joins, and transport-key denial. Use Compose's dotenv parser with an explicit authorized lookup. Parsing and Docker versus Compose env-file representability are separate gates. No implicit host lookup, shell sourcing, or global environment mutation. |
| Files, locks, migration: `utils/pathsafe.py`, `lifecycle_guard.py`, `lilrae_config_migration.py`; `internal/securefile`, `filelock` | Loading stays read-only. Explicit migration holds the existing lifecycle lock through validation, exact-byte backup, concurrent-edit check, and replacement. Preserve no-follow state access, modes/Windows ACLs, create-once versus replace, backup conflict refusal, and idempotence. Preserve caller-owned reentrancy and Python/Go lock exclusion; locking does not prove Docker ownership. |
| OS and transport: deployment boundary, `ssh.py`, `host_keys.py`, endpoint owner; ADR-034/040/066 | Keep project, pack, operator-key, and remote roots distinct. No credential/private-key bytes in argv, shell strings, URLs, or filenames. Preserve remote local-artifact refusal, certificate trust/identity checks, and fail-closed SSH pins. Validate settings without opening keys, generating trust, or contacting Docker/SSH. |
| Errors and observability: CLI `_common`, `LabResult`/startup diagnostics, deployment errors, API schemas, MCP results; ADR-065 | Map errors once at entry into existing exits, streams, and envelopes. Preserve missing/invalid, busy, timeout, cancellation, and unknown-observation outcomes. Use safe operation/category and field location; never raw decoder causes, rejected values, environment data, PEM, or remote output. Bound and sanitize unknown member names too. No parallel exception hierarchy. |
| Redaction, provenance, persistence: `utils/{redaction,logging}.py`, telemetry export, `core/provenance/providers/config_identity.py`, runstore | Reuse port 07's single Go redactor and parity corpus at outward sinks. Inject `slog`; logs use stderr. Return or handle an error without logging it twice. Preserve the allowlisted config projection and descriptor digest vectors through `internal/canonical`/`digest`. A model dump or `.env` hash is not safe provenance. |
| Assets and workflow: `_asset_manifest.py`, `hatch_build.py`, `.gitignore`, architecture model, `.ground-control.yaml` and CI | Keep generated secrets outside tracked/embedded templates and exports. Preserve existing identifiers and file contracts. Reuse the model, generated diagram, pack-ownership check, scoped test script, staged hygiene, and CI gates; add no validation workflow or policy engine. |

Keep verification mechanics separate from trust policy. The issue's single
`crypto/x509` verification owner must preserve Wazuh, SOC, and desktop rules,
including key pairing, constraints, required names, declared outputs, and the
desktop's exact-issued-leaf comparison. SSH pins are a separate authority.
Neither bundle validity nor config validity establishes authenticated readiness.
The #677, #1002, #1188, #1191, and #1413 preflights retain these guardrails.
ADR-055 remains proposed; delivered ownership checks do not prove its entire
proposed policy. Windows modes do not establish private ACLs.

The extension seams are the typed source discriminator, explicit dotenv lookup,
expected certificate identity/trust/usage, and canonical SSH endpoint/pin store.
A new field enters the same model and evidence, not a command-specific list.
Local versus SSH remains deployment transport configuration under ADR-065,
with existing wire provider identifiers retained. Use small consumer-owned
effect interfaces only where a current caller or test double requires them.
Do not fill unfinished process/redaction ports with local copies.

## Evidence, gotchas, and scope

Reuse `tests/test_config.py`, `test_config_fuzz.py`,
`test_scenario_source_config.py`, `test_cli_config.py`, migration and environment
binding tests, and `conformance/testdata/cases/{config,redaction}.txtar`.
The current config case covers only part of CLI-002. The CLI type-error test
uses a retired `containers.wazuh` field, so its rejection does not demonstrate
type checking of a current field. Delivery evidence must exercise current
fields and rejection before downstream effects, not just isolated model tests.
Closed-bug lessons #190 and #1354 require nested strictness and consistent
deployment-setting failures without traceback. #1451 requires credential-bearing
results to satisfy RAES's closed result contract as well.

Conformance cases must first pass on Python. Deliberate Go parser-policy
differences need explicit evidence; they cannot masquerade as parity cases.
Preserve a safe field location and exit 1 without traceback, with empty stdout
where that is the command contract. Config show retains its resolved-config
JSON without a result envelope. No generic error text may erase useful safe
locations, and no useful location justifies echoing input values.

Before Go, the delivery design names actual packages, components, imports,
and model changes, then passes `archcheck design` against `origin/go-cutover`.
This note does not substitute for that gate. Follow `.ground-control.yaml`,
`.gc/plan-rules.md`, `tools/run-targeted-tests.sh`, staged `pre-commit run`,
and existing CI selection. CI owns full architecture, mutation, race/shuffle,
fuzz, native-platform, and installed-lab qualification. Add Go traceability
links during delivery; retain Python links until port 31.

Non-goals are implementation, new abstractions, automatic migration/hydration,
new config/auth/error frameworks, scenario acquisition, service credential
policy, retries, remote staging, user-doc/distribution changes, and Python
behavior changes. Port 08 supplies shared operations and migration behavior;
port 10 owns commands, port 17 admission, and port 19 product credentials.
Use released RAES/env-packs Go APIs for their semantics; a missing API blocks
dependent work. Functional gaps need separate bug decisions. Target
`go-cutover`; nothing ships before port 31.
