# Issue #1465: Released Structural Factorial Experiment Tuple

Issue #1465 is the delivery contract; no requirement is attached.
This note defines adoption boundaries, not an implementation plan or a qualified
package tuple. Inspection started at `338236cc`: its lock selects `raes 9.2.0`
and `raes-env-packs 6.5.0`, while its project metadata allows version ranges.
These are inspection facts, not a supported tuple. Merged upstream source does
not establish released-package compatibility.

The governing decisions are [ADR-047](../adrs/adr-047-raes-experiment-admission-and-trial-plan-boundary.md),
[ADR-050](../adrs/adr-050-terminal-attempt-archival-and-atomic-seal.md),
[ADR-053](../adrs/adr-053-pack-backend-deployment-serving-interaction-seam.md),
and the [family adapter contract](family-adapter-contract.md).

## Ownership and migration boundary

Released RAE contracts own typed structural factorial compilation, sealed trial
plans and entries, participant configuration and control-context selection, the
shared experiment runtime, its single controller, and run/study record production.
Use the actual public APIs and corpus shipped by the selected release. This
preflight does not prescribe unreleased API names or vendor their definitions.
An unavailable required API is a dependency blocker, not permission for a local
replacement. Native GitHub blocked-by relationships remain authoritative; linked
issues retain their implementation ownership. #1465 qualifies and publishes the
final combination, without treating those separate deliveries as proof it works.

| Boundary | Canonical incumbent and required reuse |
| --- | --- |
| Admission and compilation | `core/experiment/{controller,admission,spec_loading,resolver,admission_artifacts,apparatus,bindings}.py` supply bounded loading, authorized resolution, identity joins and apparatus policy. Delegate portable semantics and structural compilation to released RAE. The current local `TrialPlan`, `PlannedTrial`, allocation expansion, seed derivation and ID hashing are migration sites, not the new public contract. |
| Public family trial | `backends/scenario_family.py`: `FamilyTrialInput`, `admit_family_trial`, `QualifiedFamilyTarget`, `AdmittedFamilyTrial`. Reuse sealed public plan reconstruction and trial instantiation. Carry selected participant configurations and control context from that same entry into execution; never rebuild them from defaults. |
| Runtime and backend | `backends/raes.py`, `raes_planning_compat.py`, `lilrae_participant_workload.py`, `raes_participant_runtime.py` and `lilrae_participant_execution.py` are the integration sites. The shared runtime owns experiment progression; one RAE runtime owner applies, delivers turns and evaluates each run. Backend adapters supply effects and observations through the selected target. |
| Records and persistence | `core/execution/{assembly,bridges}.py` and `core/archival/{context,run_record,status,coordinator}.py` currently assemble local terminal facts. Feed owner-native observations, evaluator results and evidence into released RAE run/study producers. Keep `LocalRunStore`, evidence storage, seal verification, recovery journal and read-only export as the local persistence boundary. |
| Pack and installed adapters | `core/scenario_bundle.py`, `backends/scenario_family.py` and existing purpose-specific discovery/result validators remain authoritative. Pack acquisition and validation are separate from installing executable adapters. No pack content selects Python imports. |

The existing admission controller and `core/execution/executor.py` must not
remain a second experiment engine around the shared runtime. Local wrappers may
translate inputs, enforce apparatus policy and store outputs; they must not
repeat allocation, scheduling, stopping, cancellation, retry or record semantics.
Likewise, a `RuntimeControlPlane` parameter inside a component is not itself a
second owner: inspect construction and lifetime, rather than banning symbols.
Do not revive the superseded #1447 handoff or clear resource claims. A failed
apply is terminal for that start; unknown effects do not justify another apply.
Drain participant processes before terminal record production and sealing.

`bindings.scenario_for_explicit_bindings` currently supports parameter variation
only and clears `variation_points` for that route. Do not generalize this by
discarding structural selections or their provenance. The experiment provenance
provider also reads legacy plan fields with `getattr` defaults: a new public
plan must not silently become an empty or unavailable provenance projection.
Adapt that existing provider to the public identities it actually receives.

Keep these identities separate: distribution version, schema/profile version,
authored artifact revision, validated pack version/set digest, family digest,
public plan/entry identity, instantiated snapshot digest, execution attempt and
capture-plan identity. `scenario_family.py` currently requires archive run
identity to match trial provenance; ADR-050 gives retries distinct attempt IDs.
Review the released runtime and producers' identity/lineage rules together at
this join. Preserve public trial identities and distinct attempts without
inventing IDs, replacing a public ID with a capture-plan ID, overwriting an
attempt, or rewriting sealed history. Existing archives retain read compatibility
through `archival/legacy_manifest.py`; they are not recompiled in place.

## Cross-cutting gates

All gates below apply to the adopted route, including negative and recovery
paths. Passing a RAE model validator does not satisfy the host's other gates.

| Layer and canonical owner | Required behavior |
| --- | --- |
| Authentication | The local CLI runs with operator authority. Add no listener or service for dependency adoption. Any existing API caller continues through `api/main.py`, `deps.verify_token`, `WebAuthSettings` and `middleware/bff.py` Host, CSRF and session checks. A future route also needs bounded request parsing; the runtime does not replace authentication. |
| Parser and resolver | Retain `experiment/spec_loading.py` byte/UTF-8/NUL limits and duplicate YAML/JSON key rejection, `AdmissionPolicy` aggregate/count limits, and `ProjectContainedResolver` plus `utils/pathsafe.py` no-follow contained opens. Hash and parse the same resolved bytes. Expanded structural matrices need a bound before materialization. Imports and associated artifacts must use the selected release's authorized, bounded pack/resolver closure, never ambient checkout discovery or an unverified path reopen. |
| Contract and profile validation | Use released RAE closed models, structural compiler, canonical digest/seal APIs, associated-artifact validation and public cross-artifact validators. Retain task/scenario/capture joins and backend feasibility. Reject unsupported profiles, inconsistent versions and altered sealed entries before effects. Do not flatten structural treatments into legacy scalar parameters or implement them in `extensions`, free text or scenario-name branches. |
| Configuration and capabilities | `AptlConfig`, `ScenarioSourceConfig`, `ExperimentSettings`, the binding-target manifests, `create_aptl_manifest()`, realization admission and `DeploymentBackend` remain the owners. Validate changed non-secret settings through their real consumers. An experiment cannot select arbitrary config paths, change the deployment project/provider or grant host privileges. Do not use `allow_uncertified_apparatus` or inflate manifests to qualify the release. |
| Installed adapter qualification | `require_family_capabilities` requires serving, runtime parameters, startup, capture, planning compatibility and verification from one installed distribution/version, qualified atomically for the exact pack release/family/backend. Preserve duplicate/missing/load/result failures, detached snapshots, recorded provider identity and restart/finalization drift checks. Serving still receives only ADR-053's bounded identity/component context, without runtime authority. |
| Participant selection and delivery | `experiment/bindings.py` already invokes RAE binding and participant-configuration validation. `lilrae_participant_configuration.py` validates manifest ownership, target types, configuration digest and exact prompt commitment; `lilrae_participant_workload.py` checks installed versus admitted configurations. Extend these owners for released control-context selection. A control context is not a model, credential source, tool profile, process environment or infrastructure grant. Unsupported selections fail before dispatch, without substituting a default. |
| Credentials and environment | Reuse ADR-029/052, `core/_credential_sources.py`, `EnvVars`, placeholder checks, `EnvironmentGrant`, deployment `_environment_bindings.py` and `_compose_environment.py`. Sources name the pack, consumer and variable explicitly. Structural changes can alter consumers, so recheck grants against each admitted snapshot. `value_from` output must be bound to that node; external `secret_fixture` values require OPEN environment authority. `_realization_primitives.environment_file_line` must carry values exactly or refuse them. No ambient same-name lookup or experiment-supplied secret locator. |
| Credential-bearing apply results | Preserve `raes_provisioner.closed_credential_result`, `raes_diagnostics.snapshot_after_apply`, observation reporting and the installed RAE credential-result sanitizer. Free-form details stay closed; source-image evidence stays outside credential-bearing entry payloads. Keep observed values under admitted realization authority and plan-owned values outside it. Never report an unobserved OPEN concern as observed by copying the plan, or bypass the sanitizer to accept a difference. |
| OS and process exposure | Reuse `LilraeOpenCodeExecutor`, `OpenCodeOptions`, verified tool profiles, private no-follow config files and `BoundedProcessRunner` cancellation/output/deadline/cleanup controls. Exact prompts go on stdin; credentials use explicit private delivery, never argv, URLs, logs or plan bytes. Preserve fresh private HOME/XDG state, disabled sharing/plugins/downloads and denied ambient tools/config. Existing `curl_safe` covers credential-bearing curl calls. Deployment environment files stay private; Compose receives its filtered client environment. |
| Host authority | Keep runtime materialization, orchestration-authority, resource ownership, mount/capability/network and lifecycle policy gates before backend effects. `core/execution_boundary.py` observes the selected Docker endpoint; it does not prove containment. Adapter installation is trusted Python execution, not sandboxing. Dependency qualification grants no new Docker socket, host mount, egress, physical-host or cross-seat authority; preserve ADR-060 where seats are used. |
| Persistence and integrity | Use `RunStorageBackend`/`LocalRunStore`, `utils/pathsafe.py`, evidence content storage and ADR-050's create-once seal/lock/index rules. Check public identities against existing storage and MCP/capture ID constraints before execution; reject an incompatible ID instead of sanitizing or rehashing it. Canonical owner bytes must survive storage unchanged. `SecretInvariantError` requires rejection if redaction would change identity-bearing content; do not redact and reseal it under the old digest. |
| Errors and observability | Reuse RAE `Diagnostic`, `experiment/errors.py`, `raes_diagnostics.render_raes_diagnostics`, existing provider/process errors and `LabResult`. Map new released failures at these boundaries, without a new exception tree. Output bounded codes, safe identity, counts and durations. `get_logger` does not sanitize arbitrary arguments. Shared `utils/redaction.py`, `RangeSnapshot.to_dict()`, safe provenance projections, redacting OTel export and MCP redaction remain mandatory. No raw exception/Pydantic input, authored values, credential locators, snapshots, stdout/stderr or provider responses in CLI/API/log/span envelopes. |

Model, prompt and control-context selections are experimental inputs. Their
identity can be retained without retaining operator credentials. Do not hash
low-entropy secrets as provenance or silently transform admitted values to make
serialization succeed. Capture collectors, payload validators, capture-spec
version pins, evidence loss disclosures, clock/correlation and run-scoped
provenance retain their existing owners; a run/study producer cannot fabricate
missing evidence, evaluator outcomes or successful completion.

## Release and qualification contract

Issue #1465 acceptance covers compilation and family admission on installed
wheels. Runtime execution and run and study record production belong to the
public execution entry point (#1417). The requirements in this section that
name runtime execution or records apply to that entry point.

The supported tuple must name exact released `lilrae`, `raes` and
`raes-env-packs` versions, the qualified adapter distribution/version and pack
identity, the supported profile, and the public callable/CLI entry point with
its required inputs. Qualify the actual installed OpenCode version, adapter and
capture path used by the baseline. A wheel import or mocked child does not prove
those tools interoperate. Distribution versions and extension API versions are
separate compatibility claims. Publish the tuple in the existing experiment
reference documentation; do not advertise an admission-only CLI as an execution
entry point or require consumers to construct the legacy LilRAE plan.

The issue calls for exact dependency pins. The maintainer decided to keep major
ranges in project metadata, with each floor at the qualified release. `uv.lock`
and the hashed exports carry the exact tested pins. The reference documentation
names the exact tuple for downstream pins. Keep metadata, `uv.lock`
and all applicable hashed `requirements/*.txt` exports aligned through the
configured `uv-lock`/`uv-export` owners in `.pre-commit-ci.yaml`, without manual
hash edits or editable/VCS/local upstream substitutions. `hatch_build.py`,
`src/aptl/_asset_manifest.py`, wheel and sdist assets, service/container build
inputs and offline/appliance consumers must see the same dependency closure.
Use the existing hash-verified build groups and no-isolation release toolchain;
`--no-deps` is valid only after installing the qualified dependency set.

Reuse the independent wheel fixture in `tests/fixtures/family_adapter` and
`test_family_adapter_contract.py`, plus existing experiment, participant,
credential-result, evidence and archival tests. That wheel test currently
installs host/adapter wheels over the running interpreter's dependencies and
constructs parameter-only entries; it is not yet proof of clean dependency
resolution or structural compilation. Qualification must exercise a separately
installed third-party structural family through the public route, retain exact
selected participant configurations/control context and public identities into
runtime and produced run/study records, and use no bundled concrete RAE backend
or legacy local plan. Verify imports originate from installed artifacts outside
the checkout and check resolved package consistency.

Negative evidence must cover unsupported profiles, mismatched package/provider
versions, altered seals/selections, invalid bindings and missing capabilities
before preparation or backend effects. Retain cancellation, failed apply,
evidence loss, retries and recovery without ownership leaks or false seals.
`test_raes_credential_result_contract.py` still conditionally accepts the old
payload-mismatch refusal using `hasattr`; qualification must require the fixed
behavior from the selected release. Review actual released schema/semantic
changes before refreshing corpus fixtures, frozen digests or expected IDs.
Do not make a green test by dropping fields, relaxing gates or approving new
golden values without their provenance.

Reuse `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/run-targeted-tests.sh`,
staged `pre-commit run`, `tools/check_pack_boundary.py` and its ownership ledger.
`tools/ci/select_checks.py` already selects all lanes for dependency inputs;
`.github/workflows/checks.yml` owns full checks, installed-wheel lab boot and
integration qualification. Confirm the selected artifact tests actually run in
the applicable CI/release lane; an integration marker is not execution evidence.
Keep checks and `docs/CODING_STANDARDS.md` aligned, without a parallel harness.

[The release procedure](../releasing.md) and
`release-please-config.json`/`.github/workflows/release-please.yml` own versioning,
manual candidate QA, publication, SBOM and attestations. No manual version or
CHANGELOG edits, `Release-As` footer or ad hoc publisher. Publication rebuilds
the artifacts: installed published-package verification is required to claim a
consumable tuple, alongside candidate evidence, without claiming identical bytes
unless verified. A source merge does not close this release acceptance criterion.
This preflight performs no installation, lab operation, merge or publication.

## Extensibility and non-goals

The extension input is a qualified family release and backend plus a sealed
public plan/entry, selected participant configuration/control context and capture
requirements on the existing seams. Keep runtime/storage/collector dependencies
explicit. Another supported model, prompt or structural level must not require
a new core scenario enum, per-permutation provider, credential map or ID scheme.
New profiles still need explicit released capability support and qualification.

This issue releases the baseline-capable structural/shared-runtime tuple needed
by #1415/#1417 and the first control installation. Apparatus-aware releases,
larger matrices and per-trial isolated VM infrastructure selection belong to
#1505 and the linked infrastructure-selection work. They are not baseline
blockers. Other non-goals are a new compiler, scheduler, record schema, plugin
framework, exception hierarchy, persistence service, adapter sandbox, statistical
analysis, consumer experiment design or unrelated legacy cleanup. Do not hardcode
TechVault/RPT behavior into core, add a concrete reference-backend dependency, or
weaken the generic pack/backend boundary to qualify one experiment.
