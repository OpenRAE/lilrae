# Participant request manifests

The installed package exposes `aptl.core.participant_requests`.
It publishes RAES manifests and validates complete configurations for Claude Code, Codex and managed OpenCode.
The consumer gives reviewed model profiles, role names and versioned prompt assets.
Publication does not contact a model service or load credentials.

## Public interfaces

`RequestCatalog.model_json_schema()` publishes the closed catalog and request-profile schema.
`RequestCatalog.model_validate_json()` validates a trusted consumer catalog.
Every request control is explicit.
`ParameterPolicy` records `set`, `locked`, `omit`, `unsupported` or `provider-managed`.

Only `set` and `locked` carry a value.
The owner also examines native support, numeric bounds and coupled reasoning settings.
Unknown fields, fallback requests and unsupported seed requests fail validation.

The consumer reviews a profile before it gives the catalog through trusted entry assembly.
An experiment factor can select an admitted profile.
It cannot add profiles, change their definitions or load a validator from an authored name.
Each profile has a version, review reference and canonical content digest.

If its definition changes, both the manifest and configuration commitments change.

See [compose participant requests](participant-request-operations.md) for trusted assembly.


`context_domains` maps authored slot names to exact SDL declaration references and ACT-620 asset pins.
The public `control_context_asset_reference()` helper creates these pins from admitted descriptors.
LilRAE has no built-in role or prompt catalog.
The profile's `context_order` names every declared slot exactly once.

Its placement is `stdin-prefix`.
Returned content remains separate ordered strings, without an implicit separator or template.

## Configuration targets

| Target | Type | Meaning |
| --- | --- | --- |
| `model.identifier` | String | Requested model for a decision-only Claude Code or Codex implementation |
| `model` | String | Requested provider/model identifier for OpenCode |
| `request.profile` | String | Exact `profile_id@version` from the trusted catalog |
| `request.profile_digest` | String | Canonical SHA-256 commitment to that complete profile |
| `context.<slot>` | String | One exact declaration from the slot's typed control-context domain |

All targets must have explicit selections.
Profiles disclose controls that remain provider-managed or unsupported.
The profile must match the selected model.
RAES `realize_participant_configuration(..., validator=owner)` validates a fixed selection.

For factorial selections, the public RAE trial compiler accepts the owner/version map as `participant_configuration_validators`.
The compiler calls `for_scenario()` for each concrete trial.
Each participant receives a separate sealed result and digest.
Model and prompt factors can therefore vary independently across participant addresses.

The older `ExperimentController` path must also have trusted owner validation.
Trusted assembly must give a `ParticipantManifestBinding` with its validator.
For manifests loaded from artifacts, the injected artifact-source factory can attach that validator to the resolved binding.
Missing validation rejects admission.

Resolved bindings use the canonical manifest digest, separately from the acquired file checksum.
The artifact's validator name never authorizes executable discovery.

## Request support and limitations

| Control | Claude Code | Codex | OpenCode |
| --- | --- | --- | --- |
| Gateway | Anthropic API | OpenAI API | OpenRouter API |
| Alternate serving route | Unsupported | Unsupported | Explicit requested provider, with no fallback |
| Reasoning | The reviewed effort applies. Disabled reasoning and budgets are unsupported | The reviewed disabled mode or effort profile applies. Budgets are unsupported | Reviewed model-specific disabled mode, effort or budget profile |
| Temperature and top-p | Unsupported | Unsupported | Explicit values, locks or required omissions |
| Seed | Unsupported | Unsupported | Unsupported |
| Generation limit | Explicitly provider-managed | Explicitly provider-managed | Required integer request limit, 1–32768, with declared scope |
| Usage | Provider reports when available | Provider reports when available | Provider reports when available |

Effort names are implementation-specific.
Claude profiles accept `low`, `medium`, `high`, `xhigh` and `max`.
Codex and OpenCode profiles accept `none`, `minimal`, `low`, `medium`, `high` and `xhigh`.
The trusted profile declares the reviewed setting for its exact model and build.

Syntax acceptance alone does not establish model support or account access.
Current model IDs need no date suffix.
An alias or date suffix does not attest an immutable provider snapshot.
The manifest records implementation identity, executable version and SHA-256 separately from the requested route.

The route records gateway endpoint and requested serving provider separately from actual serving identity.
Actual identity remains unattested when the provider gives no adequate evidence.
An absent usage value remains unknown. The adapter does not report it as zero.
Claude and Codex expose their latest per-handle counters through `adapter.usage(handle)`.

The launch's optional `run_store` is an existing `RunStorageBackend`.
It keeps allowlisted invocation reports in `workbench/usage.jsonl`.
The browser workbench gives its existing local run store automatically.
Missing or invalid counts become null. Reported zero stays zero.
These counts have the native CLI's reporting scope, which can include auxiliary work.

These reports exclude raw provider payloads and prompt content.
The seed limitation does not imply deterministic output.

The owner creates a native request through `prepare_request()` after content verification.
`DecisionAgentLaunch.request` and `OpenCodeOptions.request` accept the immutable request.
Trusted assembly must also give `request_binding=ParticipantRequestBinding(owner, expected_participant_address)`.
That owner and expected address must remain independent of the reconstructed request.

The dispatch boundary rechecks the trusted manifest, participant address and native SDL scope against the retained content.
Equal bytes and asset pins cannot authorize a peer participant.
An expanded request without this binding fails before provider work.
Existing native adapters apply its explicit profile and exact prompt prefix.

They verify the executable pin before provider work.
The configured OpenCode factory accepts the published manifest with the request's configuration and `prompt_ref`.
It must have an explicit invocation timeout for this path.
The managed credential-source context forwards that limit and keeps its existing credential boundary.

Existing validator-version-2 configurations keep their original checks.
`aptl.workbench.trial_participants.prepare_trial_participants()` prepares all roles from one sealed `TrialUnitRequest`.
It also receives the instantiated scenario, retained `TrialAttemptDecision`, pinned experiment model, trusted owners and approved resolved content.
The factory examines plan, entry, run, attempt, snapshot and authoring identities before credential acquisition.

`managed_trial_participants()` acquires new executors and applies their exact model, route, profile and prompt.
Its required `invocation_timeouts` mapping gives each role's installed action limit, separately from the original attempt deadline.
The trial application uses the shortest admitted action timeout for each role and validates these limits before placement or credential acquisition.
Each trial must also have a configured evidence sink before placement or credential acquisition.

Each sealed OpenCode request profile must include `assistant_turn_limit` with an explicit `set` or `locked` count.
The count bounds native assistant turns per invocation. Experiment logical steps keep their separate meaning.
An absent native turn limit fails trial preparation. It does not select a default.
`ManagedTrialParticipantApplication` installs those executors through `LilraeTrialUnit.participants` before RAE advances the trial.

The serving unit refuses a published complete OpenCode configuration without that installed application.
It keeps the same executors across pending deliveries and releases them after verified terminal cleanup.
The already admitted native bindings keep their action, tool and exposure authority.
`aptl.core.trial_participants.PendingTrialParticipant` carries the sealed configuration for an admitted binding before credential acquisition.

It refuses dispatch until the trial application installs its managed executor.
It must have an operator-supplied cancellation-and-drain callback before it releases credential leases.
The original attempt deadline remains shared across invocations.
The logical horizon comes from the pinned episode control and is enforced against the declared stepped clock.

The native assistant-turn ceiling comes from the sealed request profile. The two counters remain distinct.
The new factory must have native delivery evidence for successful invocations.
Existing manually configured executors keep optional native history when the source is present.
The invocation evidence exposes `native_history` and exact trial/configuration coordinates through its existing sink.

Native observations contain prompt agreement, recorded model, native identifiers, timings, token categories and estimated cost.
They exclude raw chat, reasoning, tools and credentials.
`native_history.unavailable_fields` names missing control, provider-generation, served-identity and billing observations.
`native_history.require_fields()` refuses a capture claim that this source cannot satisfy.

Native history must not be described as an HTTP request log.
The older `prompt_ref` and `prompt_sha256` controls commit stdin only.
They do not establish SDL asset scope or the full effective request.
Harness instructions, tool schemas, history, auxiliary requests and native retries remain separate limitations.

These limitations remain in the public manifest before selection.

## Content verification

`owner.verify_content()` accepts the sealed result, expected participant address, and resolved bytes keyed by slot.
The [request composition guide](participant-request-operations.md#verify-content-and-dispatch) gives the operating sequence.
The approved artifact resolver remains responsible for acquisition and containment.
Verification makes no network or filesystem request.
It examines the manifest and configuration digests, exact retained asset pin, participant scope, checksum, byte count and UTF-8 encoding.

Changed bytes, stale descriptors, missing slots and peer configurations fail.
The returned strings keep the exact bytes and declared slot order.
`prepare_request()` concatenates those strings. It adds no separators.
Authors include any required separators in their pinned content.

An explicitly pinned empty asset can represent an absent playbook in a fixed slot set.
It is not an implicit default.
Profiles can declare exact `unresolved_placeholders` tokens from the producer's template vocabulary.
Their presence in verified content fails preparation and reconstructed-request validation before dispatch.

An empty declaration means the producer declares no template tokens. Ordinary braces remain literal authored content.
The immutable request keeps each descriptor and ordered content string.
Reconstruction rechecks their selected asset pins, checksums and exact composition.
A different prompt and its hash do not change the selected content commitment.

Selection and content verification do not authorize disclosure or prove delivery.
The existing ACT-620 exposure and runtime gates remain required.

## Compatibility evidence

`pyproject.toml` declares the supported dependency tuple. `uv.lock` pins it.
`tests/test_participant_request_manifests.py` exercises public installed imports and native RAES schema round trips.
It also compiles fixed controls and independent per-participant factorial choices for all three implementations.
Installed dispatch tests cover Claude Code and Codex native arguments and exact prompt prefixes.

Real installed CLIs also transmit the selected reasoning settings to local fake API endpoints.
The pinned OpenCode launcher also transmits selected controls to a local fake provider from an installed wheel.
Negative tests cover profile commitments, unsupported controls, participant scope and prompt bytes.
Dispatch regressions reject peer configurations and incompatible participant scope even when prompt bytes and asset commitments are unchanged.

Shared Python and TypeScript parity tests keep safe numeric usage and redact credential-shaped replacements.
Immutable run-store tests keep manifest and configuration identity.

See the [architecture](../architecture/participant-request-manifests.md) for trust boundaries and [request qualification](../testing/participant-request-1419-qualification.md) for installed compatibility evidence.

## Actual provider observation

Sealed trial execution must also have `request_observation` in invocation evidence.
The approved local plugin observes serialized provider requests and examines the safe controls and authored-prefix commitment before it forwards requests.
It records ordered content hashes. It does not keep message text, reasoning, tool capabilities or credentials.
Each call has a sequence number, state, timing, controls and available generation/model/provider/usage/cost response metadata.

The invocation gives exact action, participant, run, attempt, entry and configuration joins.
Native step usage and provider-call usage are separate sources. Do not sum both.
The complete typed serialization is `TypeAdapter(OpenCodeInvocationEvidence).dump_json(record)` from Pydantic.
`request_observation.require_fields()` rejects unavailable required observations.

Provider claims do not establish an immutable model snapshot or billed cost.
Missing plugins, changed controls and mismatched authored prefixes fail before provider forwarding.
Failed and interrupted calls keep safe partial membership.

Nullable response fields carry `missing_value_reason`: the provider did not report a usable value, or it was not safe to keep.
Required observation is qualified on Linux and refuses unsupported platforms before launch.
The journal limit is 16 MiB with 128 KiB records. The serialized-request limit is 1 MiB.
A bound violation fails capture or forwarding. The adapter does not truncate a successful record.

Provider-call token reports are necessary for completed-call accounting.
Native estimates or placeholder zeros cannot replace missing provider usage.
