# Issue #1414 RPT Family Adapter Preflight

This note guides [issue #1414](https://github.com/OpenRAE/lilrae/issues/1414).
The supplied issue is the contract; there is no linked requirement.
The inspected baseline is `f1d754a9`. This is design guidance, not an
implementation plan or a claim that third-party family support already works.

Build on ADR-029, ADR-044, ADR-047, ADR-053, the
[#980 adapter preflight](issue-980-pack-adapter-install-seam-preflight.md), and
the [EXP-005 binding boundary](exp-005-safe-parameter-binding-provenance-preflight.md).
No new plugin framework, scenario schema, evidence store, or controller is needed.

## Ownership and public surface

LilRAE owns contracts, installed-provider admission, validation, lifecycle order,
backend effects, evidence persistence, and error normalization. RPT owns the
TechVault-family behavior and its qualification evidence. Adapter ownership is
not restricted to the backend repository: the bundled-ownership statements in
`aptl_techvault/README.md` and `validation/scenario_verification.py` must not
become a constraint on the new public contract.

Retain purpose-specific entry points and their existing spellings and selector
meanings. Names narrow discovery; they are neither executable locators supplied
by a pack nor complete compatibility claims.

| Capability | Canonical contract and discovery boundary |
| --- | --- |
| Serving | `backends/pack_interaction.py`, `pack_interaction_discovery.py`; `aptl.pack_backend_interactions`, `<pack_id>.<backend.target_name>`. Preserve total exact component membership, safe operator groups, and immutable copied results. Serving cannot change realization. |
| Runtime parameters | `backends/scenario_runtime_parameters.py`; `aptl.scenario_runtime_parameters`, `<pack_id>`. Declare runtime-owned bindings; RAES owns parameter typing and instantiation. |
| Startup and observation | `backends/scenario_startup.py`, `scenario_runtime_hooks.py`, `scenario_startup_policy.py`, `scenario_service_policy.py`; `aptl.scenario_startup`, `<pack_id>`. Cover fixed preparation/retry/reset slots, runtime realization/readback, health dependencies and image integration already used by TechVault. |
| Capture and evidence | `backends/scenario_capture.py`, `scenario_capture_discovery.py`, `core/evidence/protocol.py`, `core/evidence/adapters/sources.py`, `core/experiment/capture_registry.py`; `aptl.scenario_capture`, `<pack_id>.<backend.target_name>`. Cover declarations, source construction, transcript finalization/readback and proposition interpretation. |
| Semantic verification | `validation/scenario_verification.py`, `scenario_verification_discovery.py`; `aptl.scenario_verifiers`, `<scenario.identity>.<backend.target_name>`. Preserve atomic `QualifiedTarget` matching, prerequisites, bounded operations and `passed`/`failed`/`blocked` reports. Scenario identity need not equal pack ID. |
| Release-specific planning compatibility | `backends/scenario_planning_compatibility.py`, its discovery module, and `raes_planning_compat.py`; `aptl.scenario_planning_compatibility`, `<pack_id>.<backend.target_name>`. Keep bounded decision data and core's lock/restore discipline; no provider planner or RAES-global mutation. |

Publish an explicit supported import/export list at these existing contract
owners, including required supporting result types and exceptions. Re-export
existing types where needed; do not copy DTOs into a second SDK. A non-underscore
module name alone does not make its internals public. Runtime contexts and
operations currently typed as `object`, dynamic method names, and the
proposition interpreter's positional arguments need documented typed protocols
within these seams. Do not expose the entire provisioner, runtime manager,
configuration, environment, project tree or run store to make extraction easy.

Concrete private dependencies to eliminate from the extracted adapter include
`_raes_runtime_container_observation`, `_runtime_concern_disclosure._disclose`,
`deployment._misp_cache_credential`,
`deployment._compose_stateful_model.artifact_source_path`, and
`evidence.adapters.sources._to_outcome`. Keep their generic work with its
current owner and expose only the bounded operation/result actually required.
Renaming or re-exporting an unrestricted internal object does not close the
boundary. Public RAES models remain RAES-owned; do not vendor their schemas.

## Family qualification and per-trial authority

Keep four identities separate:

- **Family release:** upstream-validated `PackIdentity(pack_id, pack_version,
  set_digest)`, together with the authored scenario/family reference when a
  pack contains multiple scenarios. A label, source directory, SDL hash or RPT
  distribution version cannot stand in for this identity.
- **Trial instantiation:** RAES `InstantiatedScenario`, its owner-derived
  canonical instantiated digest and `instantiation_provenance`, plus the
  admitted trial coordinate and applicable `RealizedBindingProvenanceModel`
  values. These explain which permitted variation was selected.
- **Backend:** the existing `BackendIdentity` target name/version/profile and
  declared provider/transport constraints. A Docker transport is not a backend
  capability profile.
- **Installed provider:** host-observed distribution/version, entry-point
  group/name, provider ID and extension API version for each selected seam.
  This is provenance, not scenario or family identity.

Qualify an exact family release and backend combination atomically, following
`QualifiedTarget`; never independently accept versions and digests as lists
whose cross product admits unqualified releases. Several other discovery
modules currently do exactly that, even though the verifier avoids it. Reuse
the atomic matching rule across the family route rather than creating another
compatibility vocabulary. Do not repurpose verifier `ScenarioIdentity` fields
or `content_digest` to silently mean a trial snapshot. Version changes in
meaning explicitly.

Family qualification admits only variations that owner validation admits from
that release. Core must establish the snapshot-to-family relationship from the
validated source, declared variation points, bindings and canonical RAES
identity, and compare it to pinned admission data. Provider assertions, a
matching name, or an arbitrary caller-supplied digest are insufficient. Pass
that same admitted snapshot/provenance through startup, capture, observation
and verification as each capability needs it. Serving selection uses trial
identity internally; its callback receives only the ADR-053 identity and
admitted component-address context. Never reparse the
uninstantiated SDL to decide trial behavior. No adapter identity, entry point,
release qualification or pack manifest is minted per permutation.

Reuse `experiment/bindings.py` for domain/type/plane validation and
`admission_steps.py` for canonical instantiation and feasibility. The current
explicit binding route supports parameter variation points only and requires
the complete set. Family support must not silently expand that to arbitrary
structural mutation. Participant and apparatus bindings retain their owners;
they are not scenario parameters merely because names match. An adapter may
reject an unsupported admitted variation before mutation; it cannot widen an
upstream domain, repair the input or bypass feasibility checks.

Runtime-generated bindings need an explicit ownership/collision rule against
trial bindings. Generate them once per admitted trial, validate through RAES,
and pin the effective instantiation before execution; retry must not generate
different flags or secrets. Do not overwrite admitted experiment values by
dictionary merge or patch an existing snapshot/digest. Keep values and secret
references subject to their existing disclosure policy. If an upstream
contract cannot express a required binding/provenance relationship, surface
that dependency instead of inventing a local authoring schema.

The missing seam is an explicit admitted family/trial input on existing
capability contexts, carried by the existing admission and start objects.
`PlannedTrial` currently retains a snapshot digest and realized bindings, not
the instantiated snapshot itself; flat allocation pins its instantiated digest
in the source-set projection rather than each trial. Neither a digest alone
nor reopening source bytes supplies the required handoff. Extend the existing
owner boundary without creating a second experiment executor. A frozen wrapper
does not make nested mappings or RAES objects immutable: validate and detach
provider-visible data so callbacks cannot change the admitted execution.

## Admission, failures and independent releases

Discover through installed distribution metadata, filtering selectors before
loading targets. Installation grants ordinary Python execution authority;
neither entry points nor protocols sandbox an adapter. No automatic pip/git
operation, pack-code import, `sys.path` overlay, remote discovery or network
access belongs in admission. Required capability selection must be coherent
across the selected family, trial and provider provenance, with exactly one
compatible provider for each required seam. Do not mix an unqualified bundled
surface with an external surface or choose the first installed match.
Bundled and external providers may coexist only with non-overlapping qualified
targets; duplicate matches fail, with no package-name or installation-order
priority rule.

Resolve compatibility and validate required callable shapes and declarations
before pre-start hooks, credential hydration, materialization, builds or backend
apply. RPT-required startup/serving/runtime-parameter capabilities cannot inherit
today's silent `None` or unprofiled fallback on mismatch. Preserve generic
core-only behavior where no adapter is required. Malformed metadata, wrong
API/release/backend, ambiguous/missing providers, load failure and unsupported
variation must produce distinct bounded non-success diagnostics before effects.
Post-start semantic checks still run after realization; an acquisition failure
or unavailable verifier is not a semantic pass or a detection failure.

Reuse existing seam errors and translate them into RAES `Diagnostic`,
`AdmissionRejection`, `LabResult`, collector dispositions or verifier `blocked`
at their current owners. Do not add a parallel exception hierarchy. Contain
exceptions from metadata access, factories, callbacks and result normalization,
not only `entry_point.load()`. Bound collection sizes, strings, recursion and
result vocabularies, reject malformed nested types and non-finite numbers where
inapplicable, and copy results before accepting them. In-process imports and
callbacks are not forcibly time-bounded by a clock field; retain core-owned
operation deadlines/cancellation and do not advertise hard sandbox guarantees.

Document callable API versions independently of distribution versions, RAES
dependency compatibility, and persisted report/plan schema versions. Use the
existing per-seam version constants; changed required context or qualification
semantics need an explicit compatibility decision, never reinterpretation of
old metadata. An independently released adapter declares the API it was built
for; importing the installed host's current version constant must not silently
upgrade that declaration. Supported package ranges alone do not qualify pack
content.

Persist safe family identity, trial/snapshot/binding identities and each
selected provider's provenance through existing versioned records. Retry uses
the same admission. Transcript finalization must retain its provenance-drift
check in `raes_evidence_acquisition._capture_selection_from_state`; reset keeps
the separately versioned action compatibility in `_scenario_startup_runtime`.
An upgrade cannot silently rebind either to whichever adapter is now installed.
Evolve existing durable schemas/digests if needed; no alternate qualification
database or executable provider object is persisted.

## Cross-cutting passage and repository surfaces

These are implementation obligations, not assertions that current callbacks
already satisfy the public boundary.

| Layer and canonical incumbent | Required passage |
| --- | --- |
| Auth: `api/deps.py` (`verify_token`, `WebAuthSettings`), `api/middleware/bff.py`, session and workbench access gates | No new unauthenticated loader or route. Normal API/CLI ingress retains its authorization and Host/Origin/CSRF rules. Adapter contexts carry no operator bearer/session credential; runtime operations remain bound to admitted run/node ownership. |
| Configuration/source: `AptlConfig`, `ScenarioSourceConfig`, `resolve_scenario_bundle`, `scenario_bundle.py`, `_pack_staging.py`, `utils/pathsafe.py` | Keep strict `extra="forbid"`, contained `pack_directory` acquisition, no-follow bounded staging, upstream `validate_pack`/content-manifest gates and `ScenarioBundle.read_asset`. Source selection is separate from adapter installation. Do not expose import strings, scan directories for adapters, mutate staged content or duplicate pack identity validation. |
| RAES/binding/policy: public parser/instantiator/canonical digest, `experiment/bindings.py`, `admission_steps.py`, `raes_manifest`, realization and artifact-availability gates | Validate every admitted variation against the qualified source, typed domains, plane ownership, capture capabilities and planning feasibility before effects. Reuse canonical owner identities; no string substitution, alternate compiler, local schema or suppression of diagnostics. |
| Startup/env/secret: `scenario_startup` plan validation, `_scenario_environment.py`, `core/env.py`, declared account credentials, `_credential_sources.py`, `deployment/_environment_bindings.py` | Retain key/alias/uniqueness/placeholder checks, account-fixture resolution, pack/consumer/variable-scoped `EnvironmentGrant`, value classifications, single-line env-file validation and `DOCKER_TRANSPORT_KEYS` denial. Resolve trial-dependent accounts from the admitted instantiation. Pass only declared required credential values or scoped operations; never whole `.env`/`os.environ`, flags in metadata, or pack-local `.env` as operator authority. |
| Host/OS/runtime: `DeploymentBackend`, project/node receipts, `scenario_startup_policy.py`, `scenario_service_policy.py`, effective Compose validation, `curl_safe.py` | Resolve nodes through admitted ownership; retain existing service/dependency, contained artifact alias, environment-file and container-name validators. Provider policy cannot create undeclared services/edges, privileges, host ports, mounts or daemon access. Preserve network/listener/readback gates and appliance containment. Use bounded argv arrays without host-shell interpolation; credentials use stdin/private files, including curl header/body files, never argv, credential URLs or logged command strings. |
| Capture/evidence: `CollectorRegistry`, `CaptureBinding`, `CapturePlan`, `raes_evidence`, evidence coordinator/protocol/outcomes/content store | One selected registry feeds manifest projection, exact demand matching, plan digest, runtime sources and interpretation. Keep declarations non-executable; validate callbacks separately. Preserve registration/media/version/identity checks, quotas, actual capture windows, redaction, retention, loss reporting and proposition corroboration. Receipt of evidence alone proves no proposition. Do not pass the internal `NativeEvidenceRequest` wholesale: it contains a run store, project path and environment as well as useful inputs. |
| Error/logging/API envelopes: existing provider errors, `_scenario_verification_contract.py`, `raes_diagnostics`, `_raes_start_failure`, `LabResult`, `get_logger`, redaction and telemetry helpers | Public output contains stable code/phase and safe identity, counts and duration. No raw exception/Pydantic input, paths, payload, stdout/stderr or whole contexts in CLI, API, logs, spans or reports. Redaction is not path removal or input validation. Preserve verifier aggregate/report limits and collector failure dispositions. |
| Persistence/provenance: `RunRecordInputs`, `backend_evidence`, trial/capture plans, `derive_identity`, `safe_config_projection`, `LocalRunStore`, active-transcript and cleanup receipts | Use contained atomic/create-once writes, canonical identities and existing secret/seal checks. Keep secret values, credential locators and staging/host paths out of identity projections. Provider runtime authority does not include choosing archive destinations or writing another run store. |
| Packaging/host closure: `pyproject.toml`, `uv.lock`, hashed `requirements/`, `hatch_build.py`, asset manifest, appliance input owners | Installed wheels must provide all documented imports without a checkout. Moving entry points alone leaves bundled `aptl_techvault` and the tracked source copy under `aptl/_labdata`; address ownership/duplicate claims explicitly. Keep provider installation separate from pack acquisition. No vendoring RPT code or adding its data to generic build contexts. |

Also account for `aptl.evidence_payload` validators used during bundle export,
the participant desktop/smoke entry points used by the delivered family, and
stop/reset/restart paths. They must not retain a hidden dependency on the
bundled TechVault adapter. This does not require expanding the issue into a
new desktop or archival architecture. Export's registration-ID selector alone
does not establish release compatibility: preserve pinned provider provenance
and disclose unavailable semantics rather than selecting another release's
validator or claiming an unperformed semantic check passed.

Capture joins must use each instantiated snapshot's exact addresses and
requirements; a family registration referring to an absent trial node is not
automatically applicable. Keep real trial/attempt IDs distinct from capture
plan IDs. Value-bearing snapshots/provenance are runtime inputs, not safe
logging DTOs: exclude them from automatic repr, exception, span and record
dumps, and use the existing safe projections.

`tools/check_pack_boundary.py` is the canonical ownership gate and imports
installed owners; it is not a runtime-discovery template. Its
`supported_pack_id` owner discovery and explicit `--pack-directory ID=PATH`
resolution must keep working with external providers, including missing owner
sources failing closed. Keep `.pre-commit-config.yaml`,
`.github/workflows/checks.yml`, `.ground-control.yaml`, `.gc/plan-rules.md`,
`docs/CODING_STANDARDS.md` and `docs/getting-started/installing-packs.md`
consistent with the shipped contract. Extend existing `aptl.*` identifiers;
follow ADR-062 for new names, with no parallel aliases.

## Verification guardrails and boundaries

Extend the existing install-artifact, adapter-seam, plugin-pack-compatibility,
experiment-binding/admission/trial-plan, startup/runtime-parameter, capture and
verifier tests. A real separately built adapter wheel must import only the
documented public surface and work with a built LilRAE wheel outside the source
tree. `test_pack_adapter_install_artifact.py` currently adds the source root to
`PYTHONPATH` and omits a runtime-parameter entry point; that proof is insufficient
for independent release compatibility. Keep private-import checks transitive,
including supporting types and optional/finalization paths.

Evidence must cover two different admitted variations of one qualified family
release without per-variation adapter identities; exact snapshot/provenance
delivery; altered/out-of-domain/mismatched snapshots; version/digest cross-pairs;
wrong API/backend; duplicate/missing/load-failed providers; malformed nested
results; binding collisions; provider mutation; retry and restart drift; and
secret canaries across argv, logs, errors and persisted output. Negative
compatibility cases must prove no realization or pre-start effect occurred.
Use the same public conformance fixtures in supported LilRAE/adapter version
combinations, including supported older and rejected versions; same-checkout
agreement and mocked entry points alone do not establish the release contract.
Use repository-owned fixtures offline; this preflight does not authorize
accessing RPT, transferring code, installing services or publishing artifacts.

The extensibility parameter is the qualified family release plus an admitted
trial instantiation/provenance and backend identity on each existing seam.
Another admitted parameter variation must not edit a core enum, credential map,
pack manifest, proposition table or selector. A genuinely new capability or
family release still requires explicit contract compatibility/qualification.

Non-goals are implementing or moving the RPT adapter here, changing portable
SDL/pack semantics, a plugin marketplace/installer/sandbox, a catch-all adapter
object, new lifecycle/trial scheduling, broadening structural variation, a
second evidence schema/store, or rewriting unrelated core-only behavior.
Implementation must supply the generic contract and loading support plus
complete documentation and compatibility evidence; it must not claim an RPT
release is qualified without that release's evidence. Local checks stay
targeted via `tools/run-targeted-tests.sh` and staged `pre-commit run`; full
suites, coverage, whole-tree prose and clean lab qualification remain CI/CD.
