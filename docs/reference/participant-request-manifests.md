# Participant request manifests

The installed package exposes `aptl.core.participant_requests`.
It publishes RAES manifests and validates complete configurations for Claude Code, Codex and managed OpenCode.
The consumer supplies reviewed model profiles, role names and versioned prompt assets.
Publication does not contact a model service or load credentials.

## Public interfaces

`RequestCatalog.model_json_schema()` publishes the closed catalog and request-profile schema.
`RequestCatalog.model_validate_json()` validates a trusted consumer catalog.
Every request control is explicit.
`ParameterPolicy` records `set`, `locked`, `omit`, `unsupported` or `provider-managed`.
Only `set` and `locked` carry a value.
The owner also checks native support, numeric bounds and coupled reasoning settings.
Unknown fields, fallback requests and unsupported seed requests fail validation.

The consumer reviews a profile before it supplies the catalog through trusted entry assembly.
An experiment factor can select an admitted profile.
It cannot add profiles, change their definitions or load a validator from an authored name.
Each profile has a version, review reference and canonical content digest.
Changing its definition changes both the manifest and configuration commitments.

```python
from aptl.core.participant_requests import ParticipantRequestOwner, RequestCatalog
from raes_contracts.contracts import ParticipantImplementationManifestModel

catalog = RequestCatalog.model_validate_json(reviewed_catalog_bytes)
owner = ParticipantRequestOwner(
    catalog=catalog,
    context_domains=consumer_context_domains,
    scenario=admitted_scenario,
)
manifest = owner.manifest
manifest_schema = ParticipantImplementationManifestModel.model_json_schema()
registry = manifest.configuration_registry
validators = {
    (registry.owner.validator_id, registry.owner.validator_version): owner,
}
```

`context_domains` maps authored slot names to exact SDL declaration references and ACT-620 asset pins.
Use the public `control_context_asset_reference()` helper to create those pins from admitted descriptors.
No role or prompt catalog is built into LilRAE.
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

All targets require explicit selections.
Profiles disclose controls that remain provider-managed or unsupported.
The profile must match the selected model.
Use RAES `realize_participant_configuration()` with `validator=owner` for a fixed selection.
Pass the owner/version map as `participant_configuration_validators` to the public RAE trial compiler for factorial selections.
The compiler calls `for_scenario()` for each concrete trial.
Each participant receives its own sealed result and digest.
Model and prompt factors can therefore vary independently across participant addresses.

The older `ExperimentController` path also requires trusted owner validation.
Supply a `ParticipantManifestBinding` with its `validator` through trusted assembly.
For manifests loaded from artifacts, the injected artifact-source factory can attach that validator to the resolved binding.
Missing validation rejects admission.
Resolved bindings use the canonical manifest digest, separately from the acquired file checksum.
The artifact's validator name never authorizes executable discovery.

## Request support and limitations

| Control | Claude Code | Codex | OpenCode |
| --- | --- | --- | --- |
| Gateway | Anthropic API | OpenAI API | OpenRouter API |
| Alternate serving route | Unsupported | Unsupported | Explicit requested provider, with no fallback |
| Reasoning | Reviewed effort; disabled reasoning and budgets unsupported | Reviewed disabled mode or effort profile; budgets unsupported | Reviewed model-specific disabled mode, effort or budget profile |
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
Actual identity remains unattested when the provider supplies no adequate evidence.
Missing usage remains unknown, never zero.
Claude and Codex expose their latest per-handle counters through `adapter.usage(handle)`.
Pass an existing `RunStorageBackend` as `run_store` to retain allowlisted invocation reports in `workbench/usage.jsonl`.
The browser workbench supplies its existing local run store automatically.
Missing or invalid counts become null; reported zero stays zero.
These counts have the native CLI's reporting scope, which can include auxiliary work.
Raw provider payloads and prompt content are excluded from these reports.
The seed limitation does not imply deterministic output.

The owner creates a native request through `prepare_request()` after content verification.
Pass that immutable request to `DecisionAgentLaunch.request` or `OpenCodeOptions.request`.
Also supply `request_binding=ParticipantRequestBinding(owner, expected_participant_address)` through trusted assembly.
Keep that owner and expected address independent of the reconstructed request.
The dispatch boundary rechecks the trusted manifest, participant address and native SDL scope against the retained content.
Matching bytes and asset pins cannot authorize a peer participant.
An expanded request without this binding fails before provider work.
Existing native adapters apply its explicit profile and exact prompt prefix.
They verify the executable pin before provider work.
The configured OpenCode factory accepts the published manifest with the request's configuration and `prompt_ref`.
It requires an explicit process deadline for this path.
The managed credential-source context forwards that deadline and retains its existing credential boundary.
Existing validator-version-2 configurations keep their original checks.
Issue #1420 owns automatic trial-start assembly and broader actual-request evidence.
The older `prompt_ref` and `prompt_sha256` controls commit stdin only.
They do not establish SDL asset scope or the full effective request.
Harness instructions, tool schemas, history, auxiliary requests and native retries remain separate limitations.
These limitations remain in the public manifest before selection.

## Content verification

Call `owner.verify_content()` with the sealed result, expected participant address and already resolved bytes keyed by slot.
The approved artifact resolver remains responsible for acquisition and containment.
Verification makes no network or filesystem request.
It checks the manifest and configuration digests, exact retained asset pin, participant scope, checksum, byte count and UTF-8 encoding.
Changed bytes, stale descriptors, missing slots and peer configurations fail.
The returned strings preserve the exact bytes and declared slot order.
`prepare_request()` concatenates those strings without adding separators.
Authors include any required separators in their pinned content.
The immutable request retains each descriptor and ordered content string.
Reconstruction rechecks their selected asset pins, checksums and exact composition.
Replacing a prompt and its supplied hash cannot replace the selected content commitment.
Selection and content verification do not authorize disclosure or prove delivery.
The existing ACT-620 exposure and runtime gates remain required.

## Compatibility evidence

The supported dependency tuple is declared in `pyproject.toml` and pinned in `uv.lock`.
`tests/test_participant_request_manifests.py` exercises public installed imports and native RAES schema round trips.
It also compiles fixed controls and independent per-participant factorial choices for all three implementations.
Installed dispatch tests cover Claude Code and Codex native arguments and exact prompt prefixes.
Real installed CLIs also transmit the selected reasoning settings to local fake API endpoints.
The pinned OpenCode launcher also transmits selected controls to a local fake provider from an installed wheel.
Negative tests cover profile commitments, unsupported controls, participant scope and prompt bytes.
Dispatch regressions reject peer configurations and incompatible participant scope even when prompt bytes and asset commitments are unchanged.
Shared Python and TypeScript parity tests preserve safe numeric usage while redacting credential-shaped replacements.
Immutable run-store tests preserve manifest and configuration identity.

See the [architecture](../architecture/participant-request-manifests.md) for trust boundaries and [request qualification](../testing/participant-request-1419-qualification.md) for installed compatibility evidence.
