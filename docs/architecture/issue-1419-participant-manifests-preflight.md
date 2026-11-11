# Issue #1419: Participant configuration manifests preflight

This historical Reference preserves the original source record.
The record below describes its own evidence date and revision, where stated.
It does not establish current behavior, implementation completion, or installed qualification.
The preserved file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/architecture/issue-1419-participant-manifests-preflight.md).
Its last recorded file change before this rewrite was `ece3505c919e`.
Current interfaces and successor decisions take precedence for present use.


This note fixes boundaries for publishing installed participant manifests; it
is not an implementation plan or evidence that the providers are qualified.
The supplied issue contract includes managed OpenCode alongside supported
Claude Code and Codex participants. No new ADR or configuration framework is
needed. ADR-025, ADR-029, ADR-033, ADR-044, ADR-047, ADR-052, ADR-064 and
ADR-065 retain their existing owners.

This issue supersedes the [#862 preflight](issue-862-explicit-participant-model-selection-preflight.md)
where it excludes model factors, makes project-wide model configuration the
only selection authority, or requires immutable-looking model names. Its
isolation, secret-handling and decision-admission rules remain. The
[#1504 preflight](issue-1504-managed-opencode-preflight.md) and
[managed OpenCode design](managed-opencode.md) own that implementation's build,
transport and lifecycle boundaries. Native GitHub blocked-by relations remain
authoritative; this note does not clear the three supplied dependencies.

## Decisions and reuse

**Publish implementation contracts, and bind configurations per participant.**
Reuse RAES `ParticipantImplementationManifestModel`, its
`ConfigurationTargetRegistryModel`/`BindingOwnerModel`,
`ParticipantConfigurationResultModel`, and
`ParticipantImplementationSelectionModel`. Use the public RAES schema and
configuration realization/selection validators, not local copies. Publish
usable public imports and installed artifacts with owner/validator versions
and compatibility evidence; checkout-only fixtures or generated manifests
that cannot be obtained from an installation are insufficient.

The incumbents are `backends/raes_participant_apparatus.py` for decision
participants and `backends/lilrae_participant_configuration.py` for OpenCode
(paths here are relative to `src/aptl/`). Extend their responsibilities without
making one execution mode impersonate the other. The decision-only manifest's
no-action-tools claim must not be copied onto a tool-enabled OpenCode executor.
Do not make a manifest vary with each role's selected treatment. A consumer
binds its own participant addresses to the appropriate installed manifest and
supplies model domains, role names, prompt assets and factor levels. There is
no red/blue role enumeration, model catalog or prompt text in the backend.

The admitted per-participant configuration is the dispatch authority.
`ExperimentSettings.participant_models` remains strict operator configuration;
it cannot overwrite a sealed trial's selection or couple every role to one
model. A fixed control uses the same realization and validation as a factorial
selection. Any project-setting contribution must be resolved into that result
before sealing, with disagreement refused rather than resolved at launch.
Preserve existing interfaces unless an explicit compatibility change replaces
them; do not create a second per-role settings tree or precedence chain.

**Keep identity dimensions separate.** Adapter/package identity, executable
build/version/digest, gateway endpoint, requested model, requested exclusive
serving route, and observed model/provider/version are different facts.
An OpenRouter alias is a request identifier, not an immutable upstream
snapshot. Syntax validation must accept current IDs within the implementation's
supported domain without interpreting a date suffix as proof of immutability.
Unknown IDs still fail owner validation. Admission proves support, not account
access or the identity of a remote execution. Provider-reported identity is
recorded with its source and limits; unavailable identity stays unavailable.
OpenCode currently does not attest served model/provider. Never backfill those
fields from the request or encode the model into an implementation version.

**Make the complete request contract explicit.** The registry and its owner
validator declare the following for each supported implementation/model
combination. Unsupported settings must be refused before affected dispatch,
and limitations must be available before a consumer selects that combination.

| Concern | Required contract |
| --- | --- |
| Route | Requested model, approved gateway and exclusive serving-provider restriction where supported; enforced no-fallback policy. Preference order alone is insufficient. Refuse a route guarantee the implementation cannot enforce. |
| Reasoning | Explicit supported mode/effort domain, locked behavior or required omission. Reasoning support and effort names differ by model and implementation; no universal effort scale or silent downgrade. |
| Sampling | Supported finite values and coupled restrictions, or explicit locked/unsupported/omit status for each exposed control. Do not send temperature or top-p merely because another model supports them. |
| Seed | A supported bounded seed request, or explicit unsupported/omit status. A seed is not deterministic output, a randomization allocation, or replay proof. |
| Limits | Explicit token policy, including whether a limit covers output, reasoning, or combined generation; context/truncation behavior and unsupported guarantees. Process deadline, output-byte cap and token budget remain separate controls. |
| Context | Versioned control-context selection, participant scope, asset/content commitments and admitted composition; distinguish selected asset from the full delivered request. |
| Metadata | Available usage/finish and identity facts with units, provenance and unavailability; requested limits are not measured usage. Missing counts are not zero. |

Omission is a validated instruction to omit a native parameter, not an absent
setting that permits ambient defaults. Locked values and unsupported requests
must be inspectable in the public contract, not only explained in comments.
Use existing typed RAES targets and constraints. If coupled controls require
a reviewed implementation-owned request profile, its version/content
commitment and resolved settings must participate in configuration identity.
A profile reference cannot be a mutable alias, arbitrary JSON, argv, an import,
or a provider-native configuration escape hatch. This request profile is
distinct from a workbench tool profile and a credential/containment profile.

## Exact prompt and trial binding

Reuse RAES control-context target declarations and
`raes.participant_control_context.SDLControlContextConfigurationValidator`.
`tests/fixtures/structural_family/apparatus/participant-manifest.json`, its SDL
assets and `tests/structural_family_fixture.py` already demonstrate
`control_context` references, asset ID/version/digest, content checksum, and
owner-validator injection. Compose that public validator with the
implementation's model/request validation; neither substitutes for the other.
Do not recreate scope rules in a local prompt schema.

Resolve the selected asset through its admitted source, validate its declared
role/participant scope and compatibility, and verify the actual content bytes.
An asset-envelope digest and its content checksum commit different objects.
A label plus a caller-supplied SHA-256 does not establish a compatible scoped
asset. Preserve exact UTF-8 bytes, ordering and any approved composition;
newline conversion, truncation, implicit templates or post-admission additions
must not silently change the selected treatment.

The existing OpenCode `prompt_ref`/`prompt_sha256` check commits stdin only.
It does not validate SDL asset scope or identify harness/system instructions,
tool definitions, history or the entire upstream request. Keep selected-asset,
delivered-context and harness-build commitments distinct. Disclose fixed
native context and unavailable effective-request information; refuse a
requested exact-context guarantee that cannot be met. Prompt selection grants
no tool, filesystem, observation or evaluator authority (ADR-033/065).

Use RAES realization and canonical contract digests before dispatch, then
verify participant address, implementation/manifest identity, owner/version,
configuration digest and prompt selection together. Reuse
`core/participant_binding.py`'s selection validation,
`backends/scenario_family.py`'s verified entry and detached configuration bytes,
and `backends/lilrae_participant_workload.py`'s planned-versus-installed equality
check. Reject swapped peer configurations even when their prompt bytes match.
Do not rebuild a configuration from current project settings at execution time.

The family compiler already accepts `participant_configuration_validators`
keyed by owner ID/version. The older
`core/experiment/bindings.py::_participant_configurations()` calls
`realize_participant_configuration()` without an implementation validator.
That path cannot claim semantic model/request admission from scalar shape
validation. Any supported path consuming these manifests must receive the
same trusted owner validator or refuse use; never discover executable
validators from author-supplied names. The natural extension seam is the
existing injected owner validator plus a consumer-supplied supported domain,
not another backend registry or provider switch chain.

## Cross-cutting passage and security gates

These are required invariants, not claims that the current code already meets
the expanded issue contract. Paths are relative to `src/aptl/` unless stated.

| Layer and canonical incumbent | Required passage |
| --- | --- |
| Operator ingress and auth: `core/config.py`, `cli/config.py`, `api/deps.py`, `api/routers/config.py`, `workbench/app.py`, ADR-039 | Keep configuration non-secret and manifest publication free of runtime credentials. No new API is required. Any existing web access retains bearer/session, host/origin and authorization gates and safe DTO projections; a participant cannot select its own apparatus or read a peer's context. |
| Strict project shapes: `AptlConfig`, `InstalledParticipantModels`, `core/_participant_model_ids.py` | Keep unknown-field/provider rejection, strict strings, bounded identifiers and no control/option injection. Replace immutability-shaped assumptions consistently in the shared model validator and its callers; do not relax to arbitrary strings. OpenCode's project and invocation regexes currently admit different lengths/characters; all supported IDs must pass both boundaries. |
| Artifact/parser policy: `core/experiment/resolver.py`, `AdmissionPolicy`, `spec_loading.py`, associated-artifact validation; admitted pack `resolve_pack_artifact` | Use bounded bytes, strict/duplicate-key rejection and public schema validation. Use the source's contained, digest-verifying resolver; no remote fetch, arbitrary scheme, symlink escape, ambient file discovery, or reopen after hashing. A content URI in an asset is not authorization to fetch it. |
| Binding safety: `core/experiment/bindings.py`, RAES target/registry validators | Preserve `_validate_literal_safety()` and declared target types, value kinds, sensitivity, required values and duplicate-target rejection. Model/profile/prompt labels are data, never paths, environment references or executable locators. Prompt text is asset content, not a literal binding used to bypass these checks. Reject booleans as integer controls and non-finite numbers before canonicalization/native rendering. |
| Credentials: `ProcessEnvironmentCredentialSource`, `ProcessEnvironmentCredentialResolver`, `workbench/participant_source_binding.py`, `EphemeralCredentialBroker`, ADR-052 | Resolve only the configured source and selected native delivery alias. Keep placeholder/NUL checks and minimal leases; no saved login, ambient source chain, token in manifest/configuration/digest, or credential-dependent public schema discovery. Model route does not choose a secret source. |
| Environment shapes: `opencode_configuration.validate_provider_environment()`, `opencode_environment()`, `workbench/profiles.py`, `agent.py` private MCP config checks | The managed OpenCode factory accepts empty caller environment and injects only its admitted credential. Request controls use typed renderer inputs, not arbitrary environment maps. Preserve minimal HOME/XDG/provider environments and exact MCP `{command,args,env}` shape, aliases and runtime-environment allowlists. These are not deployment `EnvironmentGrant`s; do not route participant settings through Compose `.env` grants. |
| Native config/OS: `AgentLaunch`, `ProfileLaunch`, `DecisionAgentLaunch`, managed adapters, `core/opencode.py`, `render_opencode_config()`, `BoundedProcessRunner`, `utils/pathsafe.py` | Carry the sealed request through existing handoffs and provider renderers. Model IDs may be non-secret argv; credentials and prompt text may not. Keep no-shell execution, admitted executable/build pin, private no-follow files, fresh work/home/config, ambient config isolation, disabled updates/plugins/auxiliary routes, cancellation/output/deadline bounds and teardown proof. A token cap must reach the native request, not merely a launcher setting. Process supervision is not OS containment; retain the existing supported compartment/credential boundary and its limitations. |
| Tools and action auth: `profiles.verify_profile_tool_inventory()`, `core/participant_tools`, `backends/participant_tools`, common MCP `lilrae-tool-admission.ts`/`server.ts` | Decision participants stay tool-disabled with exact candidate/schema enforcement. Autonomous executors retain exact inventory, invocation-scoped token/socket/timeout validation, Ajv argument checks, one-use RAES admission and result redaction. Never pass model credentials to MCP children or let prompt/model selection widen authority. |
| Response/error boundary: `utils/strict_json.py`, `opencode_events.py`, `core/agent_errors.py`, `BoundedProcessError`, `ParticipantProviderFailure`, `core/experiment/errors.py`, RAES diagnostics/results | Treat provider output as bounded hostile input. Reuse typed parsing, stable errors and `normalize_raes_failure()`; public validation messages must exclude rejected inputs, raw provider bodies/stderr, exception chains, paths and account details. No parallel exception hierarchy. Preserve timeout/cancellation/unknown-effect distinctions and safe failure evidence. |
| Persistence/observability: `RunStorageBackend`/`LocalRunStore`, `utils/redaction.py`, common MCP `redaction.ts`, `get_logger()`, existing OTel hooks | Use allowlisted facts, shared redaction and the injected store. Immutable records use existing canonical create-once/no-follow/seal-aware writers. Blob writes do not redact; logger acquisition does not sanitize messages. No environment maps, raw generated config, prompt/reasoning/completion or replayable session IDs in public records. |

**Persistence gotcha:** both shared redactors classify keys containing `token`
as sensitive. A manifest registry key `max_output_tokens` and evidence keys
`input_tokens`/`output_tokens` therefore collide with current policy. Ordinary
JSON writes redact their values; canonical create-once writes reject any
redaction drift with `SecretInvariantError`. Prove the actual published
manifest, configuration and usage projections survive this boundary unchanged.
Use an explicit safe projection or a narrowly typed extension at the shared
redaction owner, with Python/TypeScript parity and secret-marker cases. Do not
bypass redaction, broadly exempt `token`/`session`, or rename RAES fields in a
local schema. Hashing a payload before it is silently redacted breaks identity.

Reuse `OpenCodeInvocationEvidence` and its event reducer for native metadata,
`raes_participant_control_evidence.py` for bounded decisions, and provenance's
`safe_config_projection()`/participant owner for accepted identity. Attach
configuration/context joins and honest identity/parameter limitations to the
existing records, including failures before the first turn. Version changed
published meanings with their readers. A usage field in a dataclass alone is
not persisted compatibility evidence. Internal provider retries, fallback,
and native-action retries are separate: the pinned OpenCode build's documented
internal retry limitation must survive publication, without introducing an
adapter retry or concealing route/identity uncertainty.

## Whole-repository compatibility and evidence

ADR-064's layer map in `pyproject.toml` and
`tools/check_architecture.py` govern placement: core holds shared values and
ports; adapters own native rendering; trusted entry assembly supplies validators
and side effects. Do not import an adapter into core to make validation work.
Keep the existing participant architecture/action model and
`tools/check_lilrae_participant_architecture.py` authoritative; manifest
configuration must not introduce an alternate dispatch path.

`pyproject.toml`, `uv.lock`, hashed `requirements/`, `hatch_build.py` and
`src/aptl/_asset_manifest.py` own installed dependencies/assets.
`.gc/pack-ownership.json` and `tools/check_pack_boundary.py` keep consumer
catalogs and study behavior outside core. Publish schema/validator availability
and compatibility for the installed LilRAE/RAES/provider-build tuple, not just
source-tree imports. Retain existing public target IDs or make a documented,
versioned compatibility change; `model.identifier` and OpenCode `model` already
differ and must not acquire silently conflicting meanings.

Reuse `test_config.py`, `test_experiment_bindings.py`,
`test_lilrae_participant_configuration.py`, `test_bounded_participant_runtime.py`,
the managed adapter/OpenCode transport tests and
`test_structural_factorial_family.py` with installed-wheel conventions.
Compatibility evidence must cover a fixed control and independently selected
roles, supported model aliases without snapshot claims, changed asset/content
pins, required omissions/locked controls, incompatible settings/scope, swapped
participants, tampered digests and failure before native work. Real pinned
launcher/fake-provider tests must inspect emitted route and request controls;
synthetic argv checks alone cannot show that native options are honored.
Focused negative mutations should detect removal of owner validation, prompt
scope/digest checks, sealed-trial equality, no-fallback enforcement and safe
persistence. No new architecture model or test harness is needed.

Follow `.ground-control.yaml`, `.gc/plan-rules.md`,
`tools/run-targeted-tests.sh` and staged `pre-commit run`.
`tools/ci/select_checks.py` and `.github/workflows/checks.yml` own full checks;
common MCP changes select/rebuild all consumers, and configuration/lifecycle
changes require installed-lab qualification. Follow existing issue/PR and
traceability conventions. No version/changelog edits or live provider requests
are part of this preflight; external disclosure still requires approval.

## Non-goals and anti-patterns

No experiment/study authoring, concrete model or role catalog, prompt prose,
infrastructure-factor implementation, statistical analysis, new scheduler,
trial planner, log store, credential source, gateway client or containment
design. Existing family compilation may supply compatibility evidence without
making full infrastructure factors a release gate for these manifests.

Do not fork RAES schemas, create a parallel validator/error/workflow registry,
enable arbitrary provider options, infer support from an ID regex, accept
unsupported settings and silently drop them, or inherit ambient defaults.
Do not equate a seed with reproducibility, an alias with an immutable snapshot,
a requested route with an observed provider, stdin with the full context,
manifest compatibility with live accessibility, or successful model execution
with a successful scientific trial. Required manifests, validation, installed
compatibility evidence and operator-facing limitations belong to #1419;
downstream evidence interpretation and broader experiment delivery retain
their existing owners.
