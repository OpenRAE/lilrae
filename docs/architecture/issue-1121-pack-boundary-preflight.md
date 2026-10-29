# Issue #1121 Pack Boundary Preflight

This note guides #1121, including its RPT experiment scope. The supplied issue
is the delivery contract; no managed requirement is attached. The
inspected baseline is `49c30f86`. This is architecture guidance and an ownership
decision ledger, not an implementation plan or evidence of completed extraction.

Build on [ADR-053](../adrs/adr-053-pack-backend-deployment-serving-interaction-seam.md),
the [#980 preflight](issue-980-pack-adapter-install-seam-preflight.md), and the
[public family adapter contract](family-adapter-contract.md). This note closes
#980's deferred ownership/default/policy decisions. The
[#1414 preflight](issue-1414-rpt-family-adapter-preflight.md) and
[supported adapter imports](../reference/family-adapters.md) already cover
independent adapters; extend those owners instead of creating another SDK.

## Ownership and boundaries

LilRAE owns admission, discovery, compatibility enforcement, lifecycle order,
backend operations, host diagnostics, validation, and evidence persistence.
LilRAE keeps its TechVault adapter for the original scenarios.
RPT owns an independent copy for its TechVault PurpleTeam experiment family.
Each adapter owns its serving, startup, runtime parameters, capture, evidence
interpretation, and verification behavior for its qualified family.
Pack bytes and portable meaning retain their env-packs and RAES owners.
Generic core behavior moves behind the existing `src/aptl_techvault` boundary where appropriate.
Copy the adapter into RPT under its own package and distinct family selectors.
Keep the LilRAE copy and its distribution registrations.
RPT issue #15 and its own PR track the separate experiment adapter.
This issue's explicit retention of the bundled adapter governs packaging where
older ADR-053/#1414 wording implies removal or exclusive RPT ownership. It
does not permit a core fallback or weaken ADR-053's data-only serving boundary.

Keep pack release, authored scenario/family, instantiated trial, backend
target/profile/transport, installed distribution, operator group, and generated
artifact producer profile distinct. A Compose profile is neither an adapter
capability nor an artifact profile. Shared product integration does not make
its consumer's pack identity a core constant.

Reuse the purpose-specific `aptl.*` entry points,
`scenario_family.QualifiedFamilyTarget` for atomic family qualification,
validated `PackIdentity`, and `AdmittedScenarioStart` selections through apply
and retry. Filter selectors before loading, reject duplicate compatible claims,
and fail missing required-family capabilities before preparation. Serving stays
data-only under ADR-053; it cannot become an artifact or host-operation hook.
Installed Python is trusted code, not a sandbox. Pack acquisition does not
authorize installation, imports, or remote discovery.

Remaining leaks include `raes_runtime_attestation.py` release/projection pins,
`_raes_observation_ordering.py` comparison compatibility, and participant
action/fixture addresses and behavior. Move family policy through existing
startup/runtime observation, planning compatibility, capture and verifier seams.
Core retains native readback and RAES exact comparison. Unknown releases,
changed projections, mismatched images/content, or extra/missing values must
still fail. No plan echoing, unconditional disclosure, or general comparison
bypass; preserve the recorded upstream-removal dependencies (#1017 / rae#1285).

The public imports in `reference/family-adapters.md` are the contract inventory,
not permission to copy every import currently used by `aptl_techvault`.
`runtime_parameters.py` imports release pins from `raes_runtime_attestation`
and imports the host API constant as its own compatibility declaration;
`planning_compatibility.py` also depends on that attestation module. Relocate
family facts and declare literal supported API versions. Review supporting
imports such as manifest constants, timeout errors and cleanup helpers for
documented public support. A public facade such as `artifact_source_path`
still reaches pack-specific dispatch internally; extraction must close both
the adapter-to-core and core-to-pack dependency directions.

## Configuration and migration contract

Allow an unselected configuration for initialization, diagnostics, status and
cleanup; require explicit configured identity or explicit scenario selection
at source admission before scenario effects. Removing the default must not
make `AptlConfig()` fail at import time: its class body currently constructs
`ScenarioSourceConfig()`. Also remove the independent `env_pack_bundle()`
identity default and implicit caller selection. Neither installation order,
a sole adapter, nor a directory name chooses a scenario. Preserve explicit
development-path precedence in `resolve_scenario_bundle()`.

Keep `AptlConfig` and nested models strict under ADR-025. Migration belongs to
the existing config owner and `lilrae config` surface. It must read old JSON
before validating the new model, so it works when removed fields prevent
normal loading. Do not duplicate the legacy Pydantic schema, relax
`extra="forbid"`, or rewrite files during load, doctor, API reads or startup.
A finite historical-key conversion is not a runtime pack-selection table.

Recognize the nine historical boolean keys with their old type constraints;
unknown keys, malformed values and ambiguous selections remain errors.
Preserve unrelated settings and explicit identity; require operator selection
where the old file relied on the identity default. Do not discard a disabled
group and silently start its components. Conversion needs equivalent admitted
membership or an explicit operator choice when no supported equivalent exists.
Explain retired `mail` and `reverse` choices. Keep migration local, repeatable
and failure-atomic, with recoverable original bytes, contained no-follow access
through `utils/pathsafe.py`, and no raw config values in diagnostics.
Use its existing `create_exclusive_nofollow` and `replace_private_nofollow`
primitives for private backup and replacement; validate the complete converted
config before replacing it. Account for historically omitted toggles. Serialize
against lifecycle operations with `lifecycle_guard.lifecycle_mutation_lock`
and recheck the original bytes before replacement to detect concurrent edits.
Migration cannot acquire packs, install providers, start services, or alter
existing ownership/cleanup receipts.

Remove boolean authority from `raes_profiles`, `raes_dependency_closure`,
`core/contracts.py`, lifecycle/status/recovery consumers and validation gates.
The admitted serving mapping supplies bounded operator groups; the admitted
graph supplies membership and dependency closure. Do not move the old names
into another enum or an unconstrained dictionary. Preserve the qualified
project-tree compatibility route without forcing a default external adapter.
Stop/reset use persisted groups and backend ownership receipts even after
current scenario selection or adapter installation changes.

Align `core/assets.default_config_json`, `cli/lab_init.py`, checked-in
`aptl.json`, CLI show/validate, doctor, API `get_config`, `/config`,
`ConfigResponse`, and `web/src/lib/types.ts` with its config consumers.
Initialization must explain required selection. The provenance
`provenance/providers/config_identity.py::safe_config_projection` includes the
booleans: change its versioned projection deliberately, preserving historical
meaning and excluding credentials/locators.
Whole-config dumps or file hashes cannot replace that allowlist.

## Host requirements are admitted demand

Use one side-effect-free requirement derivation/evaluation boundary for startup
and doctor; retain `SysReqResult`, `DoctorCheck`, existing probes and their
presentation envelopes. Startup consumes the already admitted selection, not
the configured name when an explicit scenario overrides it. `host_tools`
currently selects the entire system-check step; that flag is not proof of an
OpenSearch demand. Separate generic tool prerequisites from kernel demand.

The extensibility parameter is a bounded minimum `vm.max_map_count` demand,
absent when unnecessary, on the existing admitted startup contract. Core owns
the probe; a qualified adapter supplies scenario-specific need. Combine minima
by maximum, validate integer type/range (reject booleans), and retain the value
through retry. Demand must reflect the selected admitted components after
serving selection and dependency closure; an installed provider or disabled
component contributes no demand. Another pack or minimum must not require a
product-name branch. Validate demand before preparation; run bounded probes
before builds, artifact generation or apply. The current sysctl subprocess has
no timeout, so reuse the existing host-probe timeout convention when sharing it.
Reconcile this with env-packs#440's published host-resource contract when
available in the supported dependency; do not invent SDL fields, parse private
models, or keep two authoritative demand declarations. No arbitrary sysctl or
command map, and no automatic host tuning.

Compose demand belongs to the backend's actual rendered features. Replace
`owned_wazuh_services` as the version trigger with a generic feature requirement,
sharing `compose_version` and one floor definition. At this baseline
`_compose_stateful_services` says no producer emits `!override`; ordinary
certificate/volume mounts therefore do not alone prove a need for 2.24.4.
Account for image/build overrides' `!reset` features and their actual floors.
Retain 2.24.4 wherever a selected feature needs it; prove absence before
retiring a stale trigger. Renaming the predicate or applying the floor to
every generated artifact preserves the conceptual error.

Doctor consumes the same demand without startup hooks, credential hydration,
key generation, backend preparation or apply. Reuse source resolution and
read-only admission/derivation, cleaning up only its own temporary staging;
do not build another planner. With no usable selection, report dependent
checks as unavailable/skipped with a reason while retaining base tool checks.
Acquisition/compatibility failure must remain visible, not scenario success.

Reuse `execution_boundary.observe_execution_boundary`, selected-backend runners,
and `sysreqs.docker_mode_for_containment`. Native Linux, Docker VM, remote/SSH
and unknown setting ownership are distinct. Do not probe or prescribe changes
to the CLI host's sysctl for a remote daemon. Required-but-unobserved is not an
observed pass; keep startup and doctor disclosure consistent. Never execute
`sudo sysctl` or modify OS configuration.

## File-ownership decision ledger

These are assignments for current files, not completed moves. Producer IDs are
existing authored compatibility identities: do not rename them for a scanner.
Family repetition alone is not cross-pack reuse. Shared mechanics retain their
current backend owner; a promoted producer contract needs named independent
consumers and contract tests.
In the table, **family owner** means LilRAE's `src/aptl_techvault` for its
original scenarios and RPT's own adapter package for its experiment family.
It never means that RPT takes over the LilRAE implementation. Scope producer
dispatch to the admitted provider; the copies may recognize historical producer
IDs without claiming the same pack/family selectors or sharing mutable tables.

| Existing identity or surface | Policy owner and canonical incumbent to retain |
| --- | --- |
| `techvault:wazuh-indexer-certificate-profile/v1` in `deployment/_compose_stateful_constants.py::WAZUH_CERT_PROFILES` | Family owner owns output/consumer/identity mapping. Core retains production and validation in `core/certs.py` and `deployment/_stateful_certificates.py`. |
| `techvault:wazuh-manager-certificate-profile/v1` | Same boundary; retain manager trust-root and leaf identity verification. |
| `techvault:wazuh-dashboard-certificate-profile/v1` | Same boundary; retain leaf/key matching, SAN checks and consumer-specific mounts. |
| `techvault:soc-certificate-profile/v1` in `deployment/_compose_stateful_constants.py::SOC_CERT_PROFILE` | Family owner owns service membership/names; core retains `core/soc_ca.py` crypto mechanics and validators. Its `SOC_SERVICE_REGISTRY` fallback needs the same ownership decision even without a pack identifier. A profile cannot grant every output to every consumer. |
| `techvault:ssh-access-profile/v1` in `deployment/_ssh_key_bundle.py::SSH_ACCESS_PROFILE_V1` | Family owner owns pivot relationships and authorized-key composition. Core `core/ssh.py` owns the persistent operator key, key generation and POSIX/NTFS hardening. Delegate needed public-key/output operations, not the operator home directory or private key. |
| `techvault:flag-signing-profile/v2` in `deployment/_flag_signing_keys.py::FLAG_SIGNING_PROFILE_V2` | Family owner owns token format, per-node derivation and scoring semantics. Core owns contained secret-output storage, grants and lifecycle. Preserve the create-once seed across retry; never mount or log it. |
| `techvault:wazuh-manager-config-profile/v1` and legacy config-file provenance in `deployment/_compose_stateful_constants.py` | Family owner owns family dispatch/configuration policy. Retain `core/credentials.py` secure rendering, validation and atomic writes; a path cannot select executable code. |
| `techvault:cortex-service-credentials/v1` in `deployment/_cortex_service_credentials.py` | Family owner owns family bindings. Retain backend credential production and exact environment-delivery rules; distinguish connector delivery from initializer-private output. |
| `techvault:misp-cache-credential/v2` in `deployment/_misp_cache_credential.py` | Family owner owns family bindings. Retain cache credential production, validated reuse and consumer-scoped environment delivery. |
| `techvault:misp-server-tls/v1` in `deployment/_misp_server_tls.py` | Family owner owns family bindings. Retain backend TLS delivery and certificate-alias checks. Resolve `_raes_backend_generated_artifacts.py`'s hardcoded SOC artifact address through an admitted dependency. Backend synthesis alone does not make a profile generic. |
| Release-specific attestation, ordering and participant fixture/action tables | Family owner owns family qualification/facts; core retains native readback, RAES concern projection and result validation. Compatibility cannot weaken exact observation. |
| `validation/techvault*`, participant qualification, `appliance/{policy,input_profile,input_images,access_service}.py`, `workbench/{preparation,browser_mcp}.py`, CLI validation/help and asset selectors | Family owner owns family presets/expected results. Core retains parameterized validation, appliance/seat policy enforcement, browser containment and metadata projection. Remove unnecessary explanatory pack examples; do not move generic validators merely to hide a name. |
| `core/startup_reset_state.py::_LEGACY_BASELINE_RESETS` | Core-owned historical exception. The two exact old receipt identities classify core-owned enrollment-baseline cleanup (#1179). Preserve receipt bytes, action classification and completion markers without a current adapter. This closed history table must never grow for new providers. |
| `mail` / `reverse` legacy Compose profiles | Retire undriven services/dedicated assets; an external replacement needs a named pack consumer and qualification. Reconcile mail volumes/setup, reverse endpoint rendering, MCP registrations/builds/configs, image CI and docs. Do not delete operator data or redirect a dead MCP to another service. |

`ScenarioComposeServicePolicy` aliases existing files; it does not produce
artifacts. Moving constants alone leaves `_compose_stateful_graph`,
`_compose_stateful_realization`, `_compose_stateful_model`,
`_compose_capture_config` and readback coupled. Use existing fixed startup and
generated-artifact owners. If bounded output production is missing, expose only
the needed typed operation there: admitted artifact/output references and
validated output descriptions, with core-controlled destinations and grants.
No arbitrary paths, backend objects, shell callbacks or open generator registry.
Unknown producers, unsupported shapes and missing outputs fail before use.
Do not preserve `artifact_source_path`'s current unknown-profile fallback to the
manager config directory. Parameterize existing certificate/output DTOs from
admitted declarations; output paths, visibility and consumer sets cannot be
inferred from a profile's string prefix. Backend-owned UI profiles such as `web`
remain explicit core concerns; retirement targets the undriven legacy services.

## One owner-derived policy gate

Extend `tools/check_pack_boundary.py` and `tests/test_pack_boundary_policy.py`.
The incumbent derives installed owners and pack-authored host/account/credential
facts; it does not yet enforce pack identifiers themselves. Derive identifiers
and forbidden source/import ownership from adapter-owner paths and metadata,
including the independently named RPT provider. No fixed `techvault` denylist, core pack-facts
module, or "no adapter installed" pass. Keep `--pack-directory ID=PATH` through
the admitted source resolver. Unavailable claimed owner sources fail visibly;
CI must provide each declared owner input without depending on the RPT checkout.
Tracked owner paths and `pyproject.toml` registrations establish the expected
in-tree ownership even when a distribution is absent. Installed metadata alone
cannot prove that a deleted, uninstalled or renamed owner has no forbidden
references. External test inputs must be explicit, locally available fixtures
or approved installed artifacts; no checker-driven downloads or checkout scans.

Catch literals, defaults, imports, mixed case and qualified profile IDs across
all `src/aptl`, retaining script/appliance/MCP-config coverage. Structural
import/ownership checks must complement literal matching for transitive and
constructed dependencies. Test a differently named synthetic owner so another
pack needs no checker edit. Inspect tracked source independently of wheel
membership, including deletion/missing-owner and planted-literal cases.

Every retained reference needs a reviewed ledger entry with file/symbol, owner,
purpose, allowed use and retirement condition if temporary. The historical
cleanup row is an explicit exception. No directory-wide exemptions, blanket
comment/docstring exclusions or arbitrary suppression comments. Product names
still need semantic review when an identifier check passes. Exceptions must name their owner and purpose.
The original LilRAE adapter and RPT experiment adapter remain separately maintained.

Keep the checker in `.pre-commit-config.yaml` and CI's existing hook gate;
`Makefile` / `.ground-control.yaml` already route local policy to pre-commit.
Trigger it on ownership-input/exception changes. Installed-owner loading is
trusted build-time execution, not a runtime discovery template. Contain
metadata/load/inspection failures; report path/kind/code without matched
secrets or provider exception text.

## Cross-cutting passage and canonical incumbents

| Layer | Required passage |
| --- | --- |
| Auth and API shape | Preserve `api/deps.py::{verify_token,WebAuthSettings}`, `BFFMiddleware`, session/terminal and workbench gates. Project config through `api/schemas.py` DTOs and matching web types; these response DTOs do not replace strict config validation. No unauthenticated loader/install route, operator bearer token in contexts, or new host exposure. |
| Source/config/path validation | Reuse `ScenarioSourceConfig`, `load_config`, `resolve_scenario_bundle`, `ScenarioBundle.read_asset`, `_pack_staging`, upstream `validate_pack` / content-manifest validation and `utils/pathsafe`. No duplicate pack schema, trusted directory-name identity, source/staging overlap, symlink traversal or pack-local `.env` as operator authority. |
| RAES and adapter admission | Reuse parser/instantiator, `RuntimeManager`, manifest capabilities, provisioning-plan interpretation, stateful output selection, family qualification and per-seam result validators. Preserve type/cardinality/token checks and detached inputs/results; changed required contracts need explicit API compatibility. A public-looking import alone is not a supported contract. |
| Environment and secrets | Preserve `_scenario_environment`, `core/env.py`, `_credential_sources.EnvironmentGrant`, `deployment/_environment_bindings`, `_realization_primitives.environment_file_line` and `DOCKER_TRANSPORT_KEYS` denial. Grants stay pack/consumer/variable-scoped; aliases cannot grant transport overrides. Keep exact Docker/Compose env-file readback and literal `$` handling; pass declared credentials, not whole config/environment. |
| Generated outputs and crypto | Preserve `raes_stateful_realization` output selection, graph checks, `_stateful_certificates`, `_compose_stateful_model` effective checks and native stateful observation. Retain unique outputs, contained no-follow reads/writes, private directories/permissions, valid reused key/seed material, read-only mounts, producer-private exclusion, CA/key/SAN checks and environment-delivery allowlisting. Existing path-based SSH/flag writes are not containment proof; use established safe file primitives during relocation. |
| Host, OS and backend authority | Reuse `DeploymentBackend`, `execution_boundary`, ownership labels/native-ID receipts, `_compose_ownership_override`, effective runtime/Compose validators, startup/service policy validators and appliance containment gates. Only admitted resources may change; preserve ports/mounts/capabilities, daemon selection and remote-artifact restrictions. Use bounded argv and scoped stdin/private files (`curl_safe` for requests); no host-shell interpolation, secrets in argv/URLs, logged commands or implicit OS changes. |
| Errors, logs and observability | Reuse seam errors, RAES `Diagnostic` through `raes_diagnostics.diagnostic`, `ApplyResult`, `LabResult`, `DoctorCheck`, collector dispositions and verifier reports. Use `get_logger`, redaction and existing telemetry. Emit bounded codes, safe identities, counts/durations; no raw import/Pydantic/provider/sysctl/Compose errors, rejected values, snapshots, host paths or full contexts in CLI/API/logs/spans. Doctor currently silences the raw sysreq logger; shared use must not leak through startup. No second exception hierarchy. |
| Persistence and recovery | Reuse `raes_repro.RunRecordInputs`, `backend_evidence`, `derive_identity`, `safe_config_projection`, `LocalRunStore`, active capture authority and versioned cleanup receipts. Preserve atomic/create-once records, redaction/sealing and pinned provider provenance. Retry, finalization/export and reset cannot silently rebind after upgrades. No new database, whole-config hashing or executable object persistence. |

For config errors, reuse the fixed-message handling in
`cli/_common.py::resolve_optional_config_for_cli`. Its sibling
`_load_config_or_exit` currently prints raw exception text; extending that path
must not expose removed-field values or credential locators. Pydantic's
`hide_input_in_errors` does not sanitize arbitrary `.errors()` serialization,
paths or nested exception messages. Keep API failures in existing HTTP envelopes
with bounded details; never return raw validation objects.

## Repository and qualification boundaries

Packaging closure includes `pyproject.toml` entry points/Hatch packages,
`hatch_build.py`, `_asset_manifest.py`, `core/assets.py`, `uv.lock`, hashed
`requirements/`, container build contexts and appliance inputs. Removing the
top-level package while retaining its tracked copy under `aptl/_labdata/src`
still ships it. Do not vendor RPT changes back into LilRAE or add build-time checkout or automatic installation.
The bundled original adapter remains supported independently of the RPT package. Installation and pack
acquisition remain separate choices; follow ADR-062 for new names while keeping
existing `aptl.*` contract identifiers.

Reuse `tests/fixture_pack.py` and production admission for the start proof.
Detect unexpected TechVault imports, acquisition, producer dispatch and API
calls during fixture startup, rather than mocking success. Extend focused
config/CLI/API/provenance, host-check, realization/readback, capture/cleanup and
packaging tests. Cover non-Wazuh demand, no demand, scenario override,
remote/unknown daemon, malformed capability, migration failure/idempotence and
secret canaries. Rejected admission must prove no preparation/apply effects.

`tests/test_family_adapter_contract.py` and `tests/fixtures/family_adapter`
already test public imports and independently versioned adapter wheels. Extend
that evidence: the older install-artifact test's source-tree `PYTHONPATH` and
the underscore-import check alone cannot prove stable public coverage. Require
transitive supported-import checks and isolated built-wheel execution, including
capture finalization/export, reset, optional desktop/MCP paths, duplicate/missing
providers and supported/rejected host/adapter API combinations. Distribution,
seam API, pack version/digest and durable schema versions remain distinct.
Two fixture adapter versions do not qualify an actual RPT release or prove
multiple host releases. RPT supplies external release evidence; this repo-only
preflight cannot certify it or authorize other-checkout access/data transfers.

Keep `.gc/plan-rules.md`, `.ground-control.yaml`, `docs/CODING_STANDARDS.md`,
installation/migration/prerequisite docs and CI aligned. Implementation checks
remain targeted through `tools/run-targeted-tests.sh` and staged `pre-commit run`.
Full suites, coverage, whole-tree prose and clean lab lifecycle qualification
for Compose/container/config edits belong to CI. RPT criteria remain delivery
obligations; local extraction alone cannot complete the issue.

Non-goals are implementation in this preflight, another plugin framework/SDK,
catch-all adapter, lifecycle/experiment executor, generic sysctl manager,
portable SDL/pack schema changes, new evidence store, automatic installation,
hosting/publishing, unqualified removal of family behavior, or broad renaming of
historical records.
