# Public family adapters

An adapter is an installed, trusted Python distribution.
It gives backend behavior for an exact scenario family release.
RPT can own the TechVault-family adapter independently of LilRAE.
Pack acquisition and adapter installation remain separate operations.

## Discovery and versions

Entry points accept provider instances or no-argument provider classes.
See [compose a family adapter](family-adapter-operations.md) for registration and trial assembly.
No pack field can give an import path.

| Entry-point group | Exact entry name | Callable API |
| --- | --- | --- |
| `aptl.pack_backend_interactions` | `<pack_id>.<backend.target_name>` | `1` |
| `aptl.scenario_runtime_parameters` | `<pack_id>` | `1` |
| `aptl.scenario_startup` | `<pack_id>` | `1` |
| `aptl.scenario_capture` | `<pack_id>.<backend.target_name>` | `1` |
| `aptl.scenario_planning_compatibility` | `<pack_id>.<backend.target_name>` | `1` |
| `aptl.scenario_verifiers` | `<family_id>.<backend.target_name>` | `2` |

The family ID comes from the authored scenario, which can differ from the pack ID.
Each provider must declare `family_api_version = "1"` and its literal `extension_api_version` from the table.
Imported host-version constants cannot replace literal compatibility declarations.
Distribution versions, callable APIs, family APIs, and persisted schemas have separate meanings.

The declared host dependency range must include the first release with the required public API.
The host version number alone does not qualify pack content.
Family admission compares the installed `lilrae`, `raes`, and `raes-env-packs` versions with the host and adapter requirements.
An excluded or missing release stops admission with `family-package-versions-inconsistent`.

Each provider declares `qualified_family_targets` as a nonempty tuple of `QualifiedFamilyTarget` values.
`aptl.backends.scenario_family` exports the public type.
Each value contains these exact fields:

- `pack`: `PackIdentity(pack_id, pack_version, set_digest)` from `aptl.core.scenario_bundle`.
- `family_id`: the authored family name.
- `family_digest`: the canonical RAES digest of the expanded family.
- `backend`: `BackendIdentity` from `aptl.backends.identity`, with target, version, profile, provider, and transport.

Each tuple member is one indivisible qualification claim.
Version and digest combinations cannot mix across members.
Provider identity uses a stable, bounded `provider_id`. Verifier identity uses `plugin_id`.
The pack-ownership check also verifies `supported_pack_id`.

Qualification metadata contains no snapshot values or executable locators.

Family admission must have one compatible provider for every table row.
All six providers must come from one installed distribution and version.
Missing, duplicate, malformed, incompatible, or mixed installations stop admission before backend preparation.
Legacy providers keep their existing behavior for ordinary starts.

They cannot satisfy family trial qualification.

## Sealed trial handoff

Use the [trial assembly procedure](family-adapter-operations.md#compile-and-admit-a-trial) to compose these interfaces.

The admission argument is `run=ScenarioAdmissionRun(trial=FamilyTrialInput(plan, plan_entry_id, family))`.
`aptl.backends.raes` exports `admit_raes_scenario`.
`aptl.backends.raes_start_model` exports `ScenarioAdmissionRun`.
The `plan` is a sealed RAES admitted trial plan.
The `family` is its semantically validated RAES `ExpandedScenario`.

The bundle must name the same validated pack release and authored source.
`FamilyTrialInput(..., snapshot=snapshot_bytes)` accepts an already instantiated canonical snapshot.
Core verifies that these bytes match the snapshot derived from the sealed entry.
It rejects a mismatch before provider callbacks or backend preparation.

`source=ScenarioAdmissionSource(bundle, startup_selection)` accepts a preselected source.
`aptl.backends.raes_start_model` exports `ScenarioAdmissionSource`.
A family trial omits startup selection because core selects and pins the providers.

Core compares the bundle source with the given family.
It calls the public RAES `instantiate_admitted_trial_entry` function.
That function reconstructs the plan, validates its family reference, and admits the selected entry.
Core then passes one `AdmittedFamilyTrial` through capability contexts that need scenario data.

Serving discovery uses the trial internally.
The serving callback keeps its original identity-and-address-only context under ADR-053.
The trial exposes:

- `target`: the exact family qualification target.
- `snapshot`: immutable canonical RAES snapshot bytes.
- `snapshot_digest`: the owner-derived canonical snapshot digest.
- `scenario`: a new, independent copy of the instantiated model on each access.
- `provenance`: a detached RAES trial provenance model, with coordinate, selections, bindings, and sealed plan identity.
- `participant_configuration_results`: detached RAES participant configuration results of the sealed entry.
- `identity()`: a bounded projection of family, snapshot, plan, entry, and run identities.
- `evidence()`: the qualification target, `identity()`, provider identities, selection digests, and participant configuration digests.

Snapshot and provenance values are runtime inputs.
They must remain absent from logs and repository metadata.
Core excludes snapshot bytes from automatic representations.
An adapter can keep its detached inputs. This does not change the admitted execution.

Runtime-owned parameters are resolved before plan sealing.
`aptl.backends.scenario_runtime_parameters.resolve_family_runtime_parameters(bundle, target)` gives adapter-owned values.
The resolver admits the source family with `admit_family_source` before it compares the family digest with the target.
The caller must include them in RAES admission and record their binding provenance.

LilRAE does not merge generated values into an already sealed snapshot.
More parameters on sealed trial admission cause `family-trial-parameter-collision`.
Retry reuses the existing `AdmittedScenarioStart`. It does not regenerate parameters or select a new trial.

`start_raes_scenario` accepts `AcesRunTarget(store, trial.provenance.run_id)`.
An omitted target selects configured local storage and the entry's preallocated run ID.
A different explicit archive run identity stops execution before apply.
Planning also adopts the sealed entry ID as its instantiation ID.
Core writes the exact snapshot to `trial/instantiated-snapshot.json` before apply.

Core writes safe identity and selection joins to `trial/identity.json`.
Both artifacts are private, immutable, and subject to the existing run seal.
Snapshot values can be sensitive and must stay within the approved local archive boundary.
Archive conflicts, unsafe paths, sealed runs, and storage failures stop apply.

Startup must have protected `LocalRunStore` storage for family snapshots.
The previous trial's declared cleanup must complete before the next trial starts.
Each new admission uses only its instantiated node and inventory sets.
Core must have native readback for requested facts. Unsupported or unobserved required facts do not count as verified.

The existing reproducibility record keeps safe family, trial, and selected-provider identities.

## Supported imports and callbacks

These existing owners are the supported adapter import surface.
Their private names and underscore modules are implementation details.
RAES types remain available through their own published packages.

| Owner | Supported contract |
| --- | --- |
| `aptl.backends.raes` and `aptl.backends.raes_start_model` | `admit_raes_scenario` and the optional `ScenarioAdmissionSource` for a preselected bundle and startup adapter. |
| `aptl.backends.pack_interaction` | Context, provider protocol, membership, result, and resolved-result types. `resolve(context)` returns a total mapping of admitted component addresses. |
| `aptl.backends.scenario_runtime_parameters` | `ScenarioRuntimeParameterProvider`, bounded provider error, and family runtime-parameter resolver. `resolve(bundle)` returns declared bindings or `None` before plan sealing. |
| `aptl.backends.scenario_startup` | `ScenarioStartupProvider`, plan, selection, provenance, fixed hook/capability/phase enums, hook context, environment and account-reference DTOs. |
| `aptl.backends.scenario_startup_policy` | `ScenarioComposeStartupPolicy`, `StartupHealthProbe`, and `StartupHealthDependency`. Optional `compose_startup_policy()` returns this bounded declaration. |
| `aptl.backends.scenario_service_policy` | `ScenarioComposeServicePolicy`, mount/environment/container-name DTOs, `artifact_source_path`, and `MISP_CACHE_RUNTIME_CONFIG_PATH`. Optional `compose_service_policy()` returns this declaration. |
| `aptl.backends.scenario_runtime_hooks` | `ScenarioRuntimeOperations` and `disclose_runtime_concern`. Container operations keep admitted node and ownership checks. |
| `aptl.backends.scenario_capture` | Capture contexts, contribution/provider/runtime protocols, `GeneratedOutputReference`, and `ScenarioPropositionInterpreter`. |
| `aptl.backends.scenario_planning_compatibility` | Context, bounded decision, provider protocol, permitted concern sets, and `RUNTIME_CONTAINER_DAEMON_CONCERNS`. |
| `aptl.validation.scenario_verification` | Scenario/backend identities, atomic legacy targets, verifier and operations protocols, typed checks, prerequisites, statuses, context, and report. |
| `aptl.core.experiment.capture_registry` | Registrations, registry, limits, visibility, and capture bindings. |
| `aptl.core.evidence.protocol` and `aptl.core.evidence.outcomes` | Collector context/protocol/outcome and status/disposition types. Core keeps persistence and redaction. |
| `aptl.core.evidence.adapters.sources` | `SourceResult`, `WindowedSource`, `CallableWindowedSource`, `WindowedQueryCollector`, and `source_result_to_outcome`. |
| `aptl.core.scenario_bundle`, `aptl.core.deployment.realization`, and `aptl.backends.raes_realization_model` | Existing bundle, pack identity, and admitted realization DTOs. |
| `aptl.utils.pathsafe`, `aptl.utils.logging`, `aptl.utils.redaction`, and `aptl.utils.curl_safe` | Existing public containment, logging, redaction, and credential-safe request helpers. |

Startup `resolve(bundle)` receives `bundle.trial`.
Fixed hooks receive `StartupHookContext.trial` and the delegated core operation.
Family hooks receive container operations instead of an unrestricted backend.
They receive no project path.

Family runtime callbacks use `realize_runtime(operations, nodes, *, trial)` and `observe_runtime(operations, node, *, trial)`.
Core passes detached node data and bounds container commands and timeouts.
Scoped inspection exposes selected container state and restart counts, without environment values.
It also exposes `NetworkSettings.Networks`, with only a valid `IPAddress` and bounded `Aliases` for each network.
It omits all networks when it cannot show the complete set.

An operation that core refuses before the backend call raises a `ValueError` code from `RUNTIME_OPERATION_REFUSALS`.
A scoped restart operation supports retry repair.

The service and startup policy validators remain authoritative.

Capture `resolve(context)` receives `context.trial`.
Its contribution gives registrations, declared credential keys, optional generated-output references, sources, and proposition interpretation.
`native_sources(CaptureSourceContext)` receives only declared credential keys and admitted container operations.
It receives no run store or project path.

Startup and trial acquisition both call it with this context.
`context.may_prepare` is true only for startup preparation.
A source sends state-changing stimulus only when `context.may_prepare` is true.

`read_generated_output(artifact, output)` reads only an explicitly granted, admitted output through contained file operations.

On a trial, `retain_enrollment_ids(observed)` takes a node-to-Wazuh-agent-ID map.
It returns the IDs that core retained for the same trial before the call.
Core creates the trial's record once, in the first provisioning capture of the trial.
Only that capture adds IDs, and it does not replace a retained ID.
All other contexts only read the record, which includes rebuilt sources and captures after a restart.
Thus an ID that core did not retain in the first provisioning capture cannot prove continuity.

Without a trial, `retain_enrollment_ids(observed)` uses the scenario record.
Each startup preparation capture can create that record and add new hosts to it.
It does not replace a retained ID.
Measurement contexts only read the record.

The result is `None` when the record is missing or not valid.
It is also `None` when the input is not valid or core cannot store the IDs.
Duplicate agent IDs are not valid.
`lilrae lab stop -v` clears the retained IDs.

`ScenarioPropositionInterpreter` documents the existing five positional arguments.
Its result remains subject to core's evidence and proposition checks.
Native evidence uses the sealed plan-entry ID as its planned-trial identity.

The `provisioning` attempt label identifies this startup capture stage.

Verification `run(VerificationContext)` receives `context.trial` and bounded `VerificationOperations`.
`ScenarioIdentity.content_digest` remains the family digest on this explicit family route.
The trial snapshot digest remains a separate field.
The returned `VerificationReport` must keep the scenario, backend, run, and attempt identities.

Core validates aggregate status and report bounds.

## Restart and auxiliary interfaces

A transcript provider must implement `resume_capture(ScenarioCaptureResumeContext)`.
This callback returns its capture contribution for finalization.
It receives the retained family target and safe trial identities, without snapshot values.
Core must have the original provider ID, distribution, version, and entry point.

An installation change cannot silently change the finalizer.
Capture receipts extend the existing authority record with family API `1` identity fields.

Reset receipts use cleanup-action schema `v2` when they carry a family target.
Existing `v1` receipts keep their original encoding and reader.
Family reset must have the same qualified pack and distribution.
An upgraded version also needs an explicit `supported_reset_action_versions` declaration.

Its context carries `family_target`. It does not recreate a trial or grant node authority absent from the receipt.

Optional `aptl.evidence_payload` entry points keep their registration-ID selector and retained-payload validation signature.
They validate payloads. They do not select runtime adapters or establish qualification.
Family archive validation selects these entries from the capture distribution and version recorded in the reproducibility manifest.
Optional participant desktop and MCP smoke interfaces remain in `aptl.backends.participant_desktop` and `aptl.validation.participant_mcp_smoke`.

Their published DTOs support independent adapter packages.
The adapter and required auxiliary entries form one installation.
Core refuses combined registrations from unrelated installed providers.

### Participant MCP smoke providers

An `aptl.participant_mcp_smoke_plans` entry point is named `<profile_id>.<scenario catalog_id>`.
It loads a static tuple of `McpSmokeOperation` values or a provider object.
Import the public values from `aptl.validation.participant_mcp_smoke`.
[ADR-067](../adrs/adr-067-admitted-participant-smoke-providers.md) records the decisions.

A provider has these members:

| Member | Contract |
| --- | --- |
| `extension_api_version` | The string `"1"`. |
| `checks` | A tuple of `McpSmokeCheck(check_id, server_id, tool_name)`. Discovery reads it. |
| `resolve(context)` | Returns a tuple of `McpSmokeOperation` values for the admitted inputs. |

`resolve` receives one `McpSmokeContext`:

| Field | Value |
| --- | --- |
| `profile_id`, `scenario_id`, `pack` | Admitted profile, scenario catalog ID, and pack identity. |
| `nodes` | `AdmittedNode` values: SDL node name, declared service ports, and static network addresses. |
| `grants` | `McpToolGrant` values: each admitted MCP server and its exact tool names. |
| `checks` | The readiness checks that the plan must cover. |

Use `context.node(name)` to test if a node is admitted.
Use `context.address(node, network)` to get one admitted address.
It raises `ParticipantMcpSmokeError` when the address is not admitted.

Make `resolve` a pure data transformation.
Do not start processes, inspect containers, open connections, or read credentials.
Return operations only for checks in `context.checks`.
Use only checks that `checks` declares.

The host applies these rules before it starts any MCP process:

- A required readiness check has the capability of a required narrative operation.
- A required check whose server is not admitted stops qualification.
- An optional check whose server is not admitted gets no operation and no registration.
- The plan covers each expected check once, with the declared server.
- Each tool is in the grant of its server.
- Arguments are JSON values of 64 KiB or less.

A provider needs the run MCP admission.
Lab start writes it for an env-pack start.
Without it, provider resolution fails and static plans keep their earlier behavior.

#### Migration from a static plan

Static tuples keep their behavior. No change is necessary.
To select operations from the admitted inventory, follow these steps:

1. Replace the tuple entry point target with a provider object.
2. Declare every possible check in `checks`.
3. In `resolve`, omit operations for a server that `context.grants` does not contain.
4. Replace each fixed address with `context.address(node, network)`.
5. Use `discover_participant_mcp_smoke_checks(selector)` for discovery.
   `resolve_participant_mcp_smoke_plan(selector)` refuses a provider.

## Supported release tuple

This historical tuple records structural factorial compilation and family admission.
It is not the current dependency lock or a claim of execution qualification.
The current dependency declarations and exact resolved versions are in `pyproject.toml` and `uv.lock`.

| Distribution | Version |
| --- | --- |
| `lilrae` | 9.0.0 |
| `raes` | 10.0.0 |
| `raes-env-packs` | 7.0.0 |
| CPython | 3.14 |

The tuple supports the `factorial-treatments-v1` design profile.
The historical compilation route uses `env_pack_bundle`, `load_pack_experiments`, `PackExperiment.compilation_request`, and `compile_admitted_trial_plan`.
Family admission uses `admit_family_trial` and `require_family_capabilities` from `aptl.backends.scenario_family`.
The admission family is `PackExperiment.family`.
`admit_raes_scenario` also performs family admission when it receives `FamilyTrialInput`.
The [composition guide](family-adapter-operations.md#compile-and-admit-a-trial) gives the sequence.

This tuple does not qualify execution of a compiled plan on the LilRAE backend.

It also does not qualify run and study record production.

## Compatibility evidence

`tests/fixtures/family_adapter` is the public import and packaging example.
The targeted contract test builds and installs both wheels locally without a package index.
It runs outside the source tree with actual entry-point metadata.
It exercises two snapshots under one target with two independently versioned adapter releases.

It rejects unsupported family API versions.
`tests/fixtures/structural_family` is an independent structural factorial pack and adapter.
Its installed-wheel test compiles the pack through the public env-packs and RAES APIs.
The compilation uses the family owner's apparatus manifests, not the LilRAE backend manifest.

It admits every entry and examines the retained participant configurations and trial identities.
It rejects an unsupported design profile, an unsupported backend profile, and an excluded host release.
The CI installed-artifact job runs both installed-wheel tests.
Other tests cover atomic release matching, malformed providers, missing capabilities, detached inputs, binding collisions, bounded authority, and restart drift.

This evidence qualifies the generic contract. The RPT owner gives qualification evidence for its released family and adapter.

## Optional host requirements and supporting imports

`ScenarioStartupPlan.minimum_max_map_count` declares a bounded positive integer minimum or `None`.
It defaults to `None` and does not change callable API `1`.
The startup resolver must return declarations. It must not invoke lifecycle effects.

Startup uses its admitted selection. Doctor reads the same declaration. It does not run hooks.

The `HOST_TOOLS` lifecycle capability is not necessary for kernel demand.
Core owns the kernel probe and selects the engine host boundary.
A missing demand performs no kernel probe.

`ScenarioStartupPlan.seed_script`, `required_profiles`, and `activation_profiles` are optional.
A plan without scenario seeding omits all three fields.
It also omits `seed_environment_keys` and `container_environment`.
Plan validation rejects a seed field that has no seed script.
A plan with a seed script must declare nonempty required and activation profile groups.

The seed stage uses the `post_start_configuration` preparation phase.
A `stack_environment` hook can skip that phase.
If the seed operation runs without a seed script, the lab start fails.

`aptl.core.deployment.backend.DeploymentBackend` and `aptl.core.deployment.errors.BackendTimeoutError` keep their public protocol and error roles.
`aptl.backends.identity` and the existing `raes_manifest` target constants identify the backend contract independently of distribution releases.
`aptl.core.lifecycle_cleanup.WAZUH_ENROLLMENT_BASELINE_RELPATH` names reserved core-owned historical state.
It grants no new filesystem authority. Family capture still uses its scoped output grants.

The baseline cleanup and receipt readers remain core-owned across adapter upgrades.

LilRAE keeps the original `aptl_techvault` package and its registrations.
RPT maintains `rpt_techvault` independently for its distinct PurpleTeam selectors.
The RPT copy and PR do not qualify future capture specifications or scenario variations.
