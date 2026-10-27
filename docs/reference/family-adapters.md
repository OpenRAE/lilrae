# Public family adapters

An adapter is an installed, trusted Python distribution.
It supplies backend behavior for an exact scenario family release.
RPT can own the TechVault-family adapter independently of LilRAE.
Pack acquisition and adapter installation remain separate operations.

## Discovery and versions

Register provider instances or no-argument provider classes in these existing groups.
No pack field can supply an import path.

| Entry-point group | Exact entry name | Callable API |
| --- | --- | --- |
| `aptl.pack_backend_interactions` | `<pack_id>.<backend.target_name>` | `1` |
| `aptl.scenario_runtime_parameters` | `<pack_id>` | `1` |
| `aptl.scenario_startup` | `<pack_id>` | `1` |
| `aptl.scenario_capture` | `<pack_id>.<backend.target_name>` | `1` |
| `aptl.scenario_planning_compatibility` | `<pack_id>.<backend.target_name>` | `1` |
| `aptl.scenario_verifiers` | `<family_id>.<backend.target_name>` | `2` |

The family ID comes from the authored scenario, which can differ from the pack ID.
Declare `family_api_version = "1"` and the table's literal `extension_api_version` in each provider.
Do not import host version constants to make compatibility declarations.
Distribution versions, callable APIs, family APIs, and persisted schemas have separate meanings.
Declare a host dependency range that includes the first release with the required public API.
The host version number alone does not qualify pack content.

Each provider declares `qualified_family_targets` as a nonempty tuple of `QualifiedFamilyTarget` values.
Import this type from `aptl.backends.scenario_family`.
Each value contains these exact fields:

- `pack`: `PackIdentity(pack_id, pack_version, set_digest)` from `aptl.core.scenario_bundle`.
- `family_id`: the authored family name.
- `family_digest`: the canonical RAES digest of the expanded family.
- `backend`: `BackendIdentity` from `aptl.backends.identity`, including target, version, profile, provider, and transport.

Each tuple member is one atomic claim.
Version and digest combinations cannot mix across members.
Use a stable, bounded `provider_id`; verifiers use `plugin_id`.
Also retain `supported_pack_id` for the repository's pack-ownership check.
Qualification metadata contains no snapshot values or executable locators.

Family admission requires one compatible provider for every table row.
All six providers must come from one installed distribution and version.
Missing, duplicate, malformed, incompatible, or mixed installations stop admission before backend preparation.
Legacy providers retain their existing behavior for ordinary starts.
They cannot satisfy family trial qualification.

## Sealed trial handoff

Supply `trial=FamilyTrialInput(plan, plan_entry_id, family)` to `admit_raes_scenario` in `aptl.backends.raes`.
The `plan` is a sealed RAES admitted trial plan.
The `family` is its semantically validated RAES `ExpandedScenario`.
The bundle must name the same validated pack release and authored source.
Use `source=ScenarioAdmissionSource(bundle, startup_selection)` to reuse a preselected source.
Import `ScenarioAdmissionSource` from `aptl.backends.raes_start_model`.
Omit the startup selection for a family trial; core selects and pins its providers.

Core compares the bundle source with the supplied family.
It calls the public RAES `instantiate_admitted_trial_entry` function.
That function reconstructs the plan, checks its family reference, and admits the selected entry.
Core then passes one `AdmittedFamilyTrial` through capability contexts that need scenario data.
Serving discovery uses the trial internally.
The serving callback retains its original identity-and-address-only context under ADR-053.
The trial exposes:

- `target`: the exact family qualification target.
- `snapshot`: immutable canonical RAES snapshot bytes.
- `snapshot_digest`: the owner-derived canonical snapshot digest.
- `scenario`: a fresh, detached instantiated model on each access.
- `provenance`: a detached RAES trial provenance model, including coordinate, selections, bindings, and sealed plan identity.
- `identity()`: a bounded projection of family, snapshot, plan, entry, and run identities.

Snapshot and provenance values are runtime inputs.
Do not log them or put them in repository metadata.
Core excludes snapshot bytes from automatic representations.
An adapter can retain its detached inputs without changing the admitted execution.

Generate runtime-owned parameters before sealing the plan.
Use `resolve_family_runtime_parameters(bundle, target)` from `aptl.backends.scenario_runtime_parameters` when the adapter supplies those values.
The caller must include them in RAES admission and record their binding provenance.
LilRAE does not merge generated values into an already sealed snapshot.
Additional parameters on sealed trial admission cause `family-trial-parameter-collision`.
Retry reuses the existing `AdmittedScenarioStart`; it does not regenerate parameters or select a new trial.
Pass `AcesRunTarget(store, trial.provenance.run_id)` to `start_raes_scenario`.
A different or missing archive run identity stops execution before apply.
The existing reproducibility record retains safe family, trial, and selected-provider identities.

## Supported imports and callbacks

These existing owners are the supported adapter import surface.
Their private names and underscore modules are implementation details.
RAES types remain available through their own published packages.

| Owner | Supported contract |
| --- | --- |
| `aptl.backends.raes` and `aptl.backends.raes_start_model` | `admit_raes_scenario` and the optional `ScenarioAdmissionSource` for a preselected bundle and startup adapter. |
| `aptl.backends.pack_interaction` | Context, provider protocol, membership, result, and resolved-result types. `resolve(context)` returns a total mapping of admitted component addresses. |
| `aptl.backends.scenario_runtime_parameters` | `ScenarioRuntimeParameterProvider`, bounded provider error, and family runtime-parameter resolver. `resolve(bundle)` returns declared bindings or `None` before sealing. |
| `aptl.backends.scenario_startup` | `ScenarioStartupProvider`, plan, selection, provenance, fixed hook/capability/phase enums, hook context, environment and account-reference DTOs. |
| `aptl.backends.scenario_startup_policy` | `ScenarioComposeStartupPolicy`, `StartupHealthProbe`, and `StartupHealthDependency`. Optional `compose_startup_policy()` returns this bounded declaration. |
| `aptl.backends.scenario_service_policy` | `ScenarioComposeServicePolicy`, mount/environment/container-name DTOs, `artifact_source_path`, and `MISP_CACHE_RUNTIME_CONFIG_PATH`. Optional `compose_service_policy()` returns this declaration. |
| `aptl.backends.scenario_runtime_hooks` | `ScenarioRuntimeOperations` and `disclose_runtime_concern`. Container operations retain admitted node and ownership checks. |
| `aptl.backends.scenario_capture` | Capture contexts, contribution/provider/runtime protocols, `GeneratedOutputReference`, and `ScenarioPropositionInterpreter`. |
| `aptl.backends.scenario_planning_compatibility` | Context, bounded decision, provider protocol, permitted concern sets, and `RUNTIME_CONTAINER_DAEMON_CONCERNS`. |
| `aptl.validation.scenario_verification` | Scenario/backend identities, atomic legacy targets, verifier and operations protocols, typed checks, prerequisites, statuses, context, and report. |
| `aptl.core.experiment.capture_registry` | Registrations, registry, limits, visibility, and capture bindings. |
| `aptl.core.evidence.protocol` and `aptl.core.evidence.outcomes` | Collector context/protocol/outcome and status/disposition types. Core retains persistence and redaction. |
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
A scoped restart operation supports retry repair.
The service and startup policy validators remain authoritative.

Capture `resolve(context)` receives `context.trial`.
Its contribution supplies registrations, declared credential keys, optional generated-output references, sources, and proposition interpretation.
`native_sources(CaptureSourceContext)` receives only declared credential keys and admitted container operations.
It receives no run store or project path.
`read_generated_output(artifact, output)` reads only an explicitly granted, admitted output through contained file operations.
`ScenarioPropositionInterpreter` documents the existing five positional arguments.
Its result remains subject to core's evidence and proposition checks.
Native evidence uses the sealed plan-entry ID as its planned-trial identity.
The `provisioning` attempt label identifies this startup capture stage.

Verification `run(VerificationContext)` receives `context.trial` and bounded `VerificationOperations`.
`ScenarioIdentity.content_digest` remains the family digest on this explicit family route.
The trial snapshot digest remains a separate field.
Return a `VerificationReport` with the same scenario, backend, run, and attempt identities.
Core validates aggregate status and report bounds.

## Restart and auxiliary interfaces

A transcript provider must implement `resume_capture(ScenarioCaptureResumeContext)`.
This callback returns its capture contribution for finalization.
It receives the retained family target and safe trial identities, without snapshot values.
Core requires the original provider ID, distribution, version, and entry point.
Changing the installation cannot silently change the finalizer.
Capture receipts extend the existing authority record with family API `1` identity fields.

Reset receipts use cleanup-action schema `v2` when they carry a family target.
Existing `v1` receipts retain their original encoding and reader.
Family reset requires the same qualified pack and distribution.
An upgraded version also needs an explicit `supported_reset_action_versions` declaration.
Its context carries `family_target`; it does not recreate a trial or grant node authority absent from the receipt.

Optional `aptl.evidence_payload` entry points retain their registration-ID selector and retained-payload validation signature.
They validate payloads; they do not select runtime adapters or establish qualification.
Family archive validation selects these entries from the capture distribution and version recorded in the reproducibility manifest.
Optional participant desktop and MCP smoke interfaces remain in `aptl.backends.participant_desktop` and `aptl.validation.participant_mcp_smoke`.
Their published DTOs support independent adapter packages.
Install the required adapter and auxiliary entries together; do not merge registrations from unrelated installed providers.

## Compatibility evidence

`tests/fixtures/family_adapter` is the public import and packaging example.
The targeted contract test builds and installs both wheels locally without a package index.
It runs outside the source tree with actual entry-point metadata.
It exercises two snapshots under one target with two independently versioned adapter releases.
It rejects unsupported family API versions.
Other tests cover atomic release matching, malformed providers, missing capabilities, detached inputs, binding collisions, bounded authority, and restart drift.
This evidence qualifies the generic contract; the RPT owner supplies qualification evidence for its released family and adapter.
