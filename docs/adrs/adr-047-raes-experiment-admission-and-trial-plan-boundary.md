# ADR-047: RAES Experiment Admission and Trial-Plan Boundary

## Status

accepted

## Date

2026-07-19

## Released-contract successor boundary (issue #1465)

Issue #1465 adopts released structural compilation, sealed public plans/entries, participant selections, and the shared runtime. These supersede the local plan, allocation, seed, identity, and loop designs below. A LilRAE wrapper retains bounded authorized resolution,
apparatus admission, backend integration and persistence; it must not become a
second compiler or runtime controller. Public identities are preserved, with
attempt lineage reconciled against ADR-050 and the released producer contracts.
This is an adoption guardrail, not a claim that the migration has shipped.
All parser, security, no-mutation and storage boundaries remain applicable.

## Reader boundary

This Explanation records design reasons and constraints.
Dated examples, versions, estimates, and measurements describe their stated revision.
They do not establish current interface support or installed qualification.
The [run Reference](../reference/experiment-runs.md) describes maintained use.
The record's status and amendments still determine its decision scope.

## Context

EXP-002 makes APTL the execution apparatus for experiments authored through
RAES `experiment-authoring-input-v1`. The authoring input references a RAES
`experiment-task-v1`, capture specifications, and scenario material, then asks
the apparatus to turn a bounded allocation into stable executable trials.

The architectural risk is not the allocation loop. The risks include another experiment language, late untrusted resolution, and admission paths that bypass startup or capture controls.

The repository already owns the relevant boundaries:

- `raes_contracts.experiment_spec.parse_experiment_spec` and the exported RAES
  contract models own experiment structure and model-level semantic invariants.
- `raes.parse_sdl` / `parse_sdl_file`, the RAES reference processor, and
  planner diagnostics own scenario semantics, parameter binding, realization
  requirements, and the backend capability gate.
- `create_aptl_manifest()` owns APTL backend identity and runtime capability
  claims. The RAES reference processor manifest is the corresponding processor
  identity surface.
- `start_raes_scenario()`, `AcesRunTarget`, `AcesStartOutcome`, and
  `_LAB_START_STEPS` own the existing RAES-to-lab handoff.
- `DeploymentBackend` owns Docker, Compose, host, and container operations.
- Strict `AptlConfig` owns durable non-secret configuration. `EnvVars`, `.env`
  hydration, placeholder checks, and generated config own runtime secrets.
- `LocalRunStore`, `RangeSnapshot.to_dict()`, ADR-044's reproducibility record,
  and the exporter own persistence, redaction, inventory, and packaging.
- RAES `Diagnostic`, `render_raes_diagnostics()`, `StartupDiagnostic`,
  `LabResult`, and the existing CLI/API projections own failure reporting.

Current startup ordering is important. `_LAB_START_STEPS` hydrates `.env`,
generates keys and certificates, renders service configuration, seeds volumes,
and pulls images before `_step_start_containers` plans and applies the RAES
scenario. Experiment admission cannot simply be added inside
`start_raes_scenario()`: by then APTL has already mutated local apparatus state.

## Decision

### Experiment-controller boundary

Add one experiment-controller composition boundary above lab lifecycle. It has
two distinct phases:

1. **Admission** reads bounded inputs and pins references. It invokes RAES validation/planning, checks apparatus policy, and produces canonical immutable plan bytes. Admission may stage bounded temporary inputs and persist its journal. It must not load runtime secrets, generate credentials/certificates, render configuration, acquire images, collect evidence, deploy, or start sessions.
2. **Execution** is downstream work. It receives an admitted plan and delegates
   each trial's scenario to the existing `RuntimeManager` and lab lifecycle. It
   must not re-resolve references, reinterpret the allocation, or mint a new run
   identity.

Admission is all-or-nothing across the complete allocation. No trial may start
when any source, condition, capture requirement, stochastic control, apparatus
constraint, or planned scenario fails admission. An operational retry may reuse only the exact admitted bytes. It must not parse or plan another input, preserving the existing `raes.py` retry rule.

The controller is a coordinator, not another runtime manager. Do not split it
into speculative repository, service, provider, DTO, and policy hierarchies.
Dependencies should be explicit: RAES loaders/models and processor, canonical manifests, authorized resolution, bounded admission policy, and the existing `RunStorageBackend`. Deployment is not an admission dependency.

### RAES contracts remain authoritative

The admitted graph retains RAES objects and identities directly:

- The root enters through `parse_experiment_spec`; APTL does not define a local
  authoring-input model.
- Task and capture payloads validate through the exported
  `ExperimentTaskModel` and `ExperimentCaptureSpecModel` public surfaces. The
  installed RAES fixture corpus is the contract test source; fixtures are not
  copied into an APTL-owned schema corpus.
- Import-free scenario material is parsed from the resolver's already bounded
  UTF-8 bytes with `raes.parse_sdl`; canonical scenario or
  instantiated-snapshot identity uses the RAES canonical digest API. Never
  hand the original untrusted path to `parse_sdl_file`, because doing so
  reopens it after digest verification.
- Associated-artifact manifests enter through
  `load_associated_artifact_manifest_json` and
  `validate_associated_artifact_manifest`, with caller-supplied bounded readers
  and `AssociatedArtifactValidationLimits`.
- Each unique condition binding is submitted to the public RAES reference
  processor against `create_aptl_manifest()` before admission succeeds. This is
  the planning-only seam: it does not require an APTL `RuntimeTarget`,
  `AptlConfig`, or `DeploymentBackend`. RAES planner diagnostics, realization
  support, variable typing, and semantic validation are not duplicated locally.

`parse_experiment_spec` currently applies `yaml.safe_load` before the
closed-world model and therefore does not reject duplicate mapping keys. Bound
the bytes and perform one narrow duplicate-key/ambiguous-document preflight
before calling the public loader. This is parser hardening, not a second
experiment schema: field shape and semantic rules remain exclusively with the
RAES models. Task and capture artifacts likewise use only their published
serialization format and exported RAES model; do not silently accept a second
YAML/JSON dialect.

LilRAE adds cross-artifact joins and apparatus policy after validation. These cover identity/version, unique resolution, task/scenario agreement, capture scope, parameter targets, controls, and combined apparatus constraints.
These checks must operate on RAES fields; they must not restate those fields in
local Pydantic or dataclass mirrors.

Contract schema versions and artifact versions are different concepts.
`schema_version="experiment-task/v1"` selects the RAES contract, while a
task reference's `ref_version` identifies the authored task revision. Admission
must validate and record both and must not compare one namespace to the other.
Likewise, the hyphenated identifiers in manifest
`supported_contract_versions` are not interchangeable with slash-form schema
version values.

The backend manifest remains a runtime capability declaration. Do not add
experiment authoring/task/capture contract identifiers to
`create_aptl_manifest()` merely to advertise this controller unless RAES's
backend manifest authority explicitly allows and requires them.

### Authorized artifact resolution

Experiment references are capabilities, not paths or commands. The default
resolver is offline and project-contained. It accepts only supported locators and returns bounded bytes with normalized metadata. It must not return executable objects or paths for later reopening.

For project files, build on the containment rule in
`scenario_catalog._resolve_project_file`, strengthened for untrusted experiment
inputs:

- Reject absolute paths, `..` components, NULs, non-files, and every symlinked
  path component. Resolving a path and checking its prefix is not enough because
  a symlink can change between check and open.
- Open once using descriptor-relative, no-follow semantics where the platform
  provides them. Hash and parse the exact bytes from that open handle so a
  time-of-check/time-of-use swap cannot change the admitted payload.
- Enforce per-document, per-artifact, aggregate-byte, reference-count,
  allocation-size, and nesting/depth limits before expensive parsing or trial
  expansion. RAES's associated-artifact limits remain the authority where that
  contract applies.
- Verify declared size and checksum before parsing or using a payload. Digest
  mismatch, unsupported digest algorithm, ambiguous/missing resolution, or an
  undeclared extra binding is fatal.
- Reject credential userinfo and secret-bearing query fields in every locator,
  not only associated-artifact manifests. Persist portable references and
  digests, not host-absolute paths.

RAES SDL imports are a second resolver surface. `parse_sdl(content, path=...)`
delegates imports to RAES file/OCI resolution and reopens local import files.
Imports require an authorized, complete, digest-pinned, size-bounded graph in private staging. RAES must parse only that tree and verify its import lock; otherwise admission refuses. Never let an admitted root switch from
the controller resolver to ambient RAES import discovery.

Network, OCI, or registry fetching is disabled by default. Remote resolution needs separate authorization through the same narrow contract. Its policy bounds scheme/authority, offline behavior, timeouts, redirects, bytes, authentication, and required digests. It must reject redirects to unauthorized authorities and must not
take credentials from the experiment document. Do not fall back from a failed
remote resolution to an ambient filesystem search, current working directory,
`PATH`, environment variable, or package import.

### Apparatus and capture capability admission

Task apparatus constraints and authoring-input apparatus intent are conjunctive;
the latter cannot weaken the former. Evaluate processor/backend identities,
manifest references and digests, compatibility declarations, required
capabilities, and contract versions against the canonical RAES processor
manifest and `create_aptl_manifest()` payload.

Scenario-specific feasibility remains with `RuntimeManager.plan()`. Admission must not probe Docker or Compose. Configuration flags cannot prove capabilities refused by the manifest or planner.

For admission, use the equivalent planning-only RAES reference-processor API.
`RuntimeManager.plan()` remains the execution owner. Constructing that runtime target imports configuration and deployment dependencies, so even a no-op backend violates the admission boundary.

Capture admission needs one code-owned mapping from RAES capture requirement
terms to existing APTL capture owners (`collectors.py`, MCP/Kali capture,
runtime snapshots, orchestration/evaluation history). Admission and later
execution must share that mapping. Unsupported capture kinds, channels, media, sealing, redaction, retention, or integrity must fail admission. They cannot select arbitrary collectors, imports, methods, or shell commands. The mapping describes support only. It does not replace the
RAES capture-spec model.

Participant implementation/provider selection remains behind the RAES
participant-runtime boundary and issue #557. Admission may retain and validate
a RAES red-variant selection, but it cannot resolve `agent_ref` to a Python
entry point, executable, image, environment variable, or provider method.

### Deterministic immutable trial plan

The v3 trial plan is an APTL internal execution journal, not a portable RAES
experiment, task, study, run, apparatus, capture, or analysis contract. It carries execution joins only: source identity/digests, assignments, provenance, participant configuration, safe apparatus, stochastic/episode controls, capture references, ordering, and planned IDs. Eventual portable run and apparatus records use RAES contracts;
they must not serialize this journal as if it were `experiment-run-v1`.

Expansion obeys these rules:

- A flat allocation uses ordinal `0..target_run_count-1`.
- A condition allocation follows the authored `compared_conditions` order,
  then an explicit zero-based replication ordinal. Map insertion order,
  filesystem enumeration, locale, wall clock, and process-global randomness
  have no effect.
- An `allocation_method`, stochastic-control role, or ordering behavior is
  executable only when it maps to a supported, versioned controller policy.
  Free-form text is never evaluated or silently approximated. Unknown or
  under-specified controls fail admission.
- Explicit condition bindings use RAES
  `experiment-binding-descriptors-v1`. Scenario targets use declared parameter variation points. Participant targets use their selected manifest registry. Apparatus targets use the closed native registry.
  Missing targets, canonical alias collisions, conflicting values, unsafe
  literals, and incomplete scenario variation sets are fatal.
- A seed or randomized order is derived with a documented, domain-separated
  cryptographic hash from canonical source-set identity plus logical trial
  coordinates and control ID. Do not use Python `hash()`, UUIDs, timestamps,
  ambient RNG state, or a library PRNG whose algorithm is not part of the
  policy version.
- The plan and source-set identities are digests of RFC 8785 canonical JSON
  projections. Canonical projections exclude admission time, host-absolute
  paths, temporary paths, log text, and mutable runtime state. They normalize
  digest case and sort semantically unordered maps/sets. Authored lists whose
  order is meaningful remain ordered.
- Planned IDs combine a safe prefix with a cryptographic digest. The versioned identity includes source digest, condition or flat sentinel, and replication ordinal. The same admitted
  inputs and policy version produce the same IDs on every supported host.

The in-memory plan is immutable after construction. No downstream caller may
mutate a shared list/dict or replace a referenced artifact. Before execution,
the persisted plan digest must still match the canonical bytes and every
trial's plan reference must match it.

The extensibility parameter for allocation is a small versioned ordering and
stochastic-control policy passed into the pure expander. A future supported
blocked or seeded-random allocation adds a policy mapping and conformance tests;
it does not add scenario-name branches or reinterpret old plan bytes.

### Persistence and state model

`RunStorageBackend` remains the only persistence dependency. The controller
must receive the configured store; it must not hardcode `./runs`,
`.aptl/runs`, or a third root. Trace-correlated run capture and configured run
storage currently use both roots in different paths, so EXP-002 must not deepen
that inconsistency. Callers resolve and inject one store/target, as they already
do with `AcesRunTarget`.

The existing `LocalRunStore.write_json()` performs lexical path validation and
redaction, but it is overwrite-capable, follows existing symlink components,
and emits presentation JSON rather than canonical bytes.
Immutability therefore requires a narrow create-once canonical JSON operation
on the existing run-store protocol, not a second experiment repository.
Persistence preserves scenario content, including scenario credentials and
credential-shaped identifiers. It canonicalizes once, accepts identical
existing bytes, and rejects conflicting bytes without silently changing data.
RFC 8785 is a direct runtime dependency for this operation.

Issue #557 reuses this primitive for a distinct run-scoped integrity need.
`LocalRunStore.create_run_json_once()` publishes an immutable action-evidence
transaction beneath an existing run archive. It starts its descriptor-relative
walk at the configured store root, including the run-id component, so a
pre-existing symlinked run directory cannot redirect publication. The
transaction contains both participant and evaluator projections; append-only
JSONL files are recoverable indexes, not the atomic authority. Because
publication follows an accepted RAES participant commit, archive failure is
reported without discarding or falsifying the accepted runtime snapshot.

Use an explicit plan namespace beneath the injected store. A plan ID is not a
`run_id`, and the plan must not acquire a fake `manifest.json` merely to fit
`LocalRunStore.list_runs()`. Extend the existing storage boundary narrowly
rather than teaching run listing/export code that controller journals are
runs. The operation must use descriptor-relative, no-follow publication for
every path component. Current `LocalRunStore._run_dir()` follows an existing
`<base>/<run_id>` symlink and can escape the configured root, so its lexical
containment check is not sufficient for this integrity boundary.

Persist the full admitted plan once under a controller-owned plan namespace.
Each planned trial archive stores only the plan identity/digest and its own
trial projection, then reuses the planned-trial ID as the execution `run_id`.
Do not call `_resolve_run_target()` to mint a timestamp run ID for an admitted
trial. The controller journal is explicitly APTL-internal and names the RAES
source artifacts it derives from; it is not a RAES study or run.

Admission has a one-shot result, not a parallel workflow engine:

- rejected: structured diagnostics and no plan;
- admitted: immutable canonical plan bytes, plan identity, and trial tuple.

Execution state continues through RAES operation receipt/status, runtime
snapshot, workflow/evaluation history, `ScenarioSession`, and `LabResult`.
Do not create `PENDING/RUNNING/FAILED` experiment-controller states that
duplicate those incumbents.

## Security layers

| Layer | Required behavior |
| --- | --- |
| Auth surface | Core admission performs no authentication. A local CLI caller is the current trusted operator boundary. A future admission API must authenticate and enforce BFF Host, CSRF, and session checks before resolving paths. It needs pre-parse size limits and a bounded typed request. URLs must not carry credentials. |
| Input shape | Bound the root bytes before `parse_experiment_spec`; use RAES closed-world models and validators for all RAES payloads. Reject unknown versions and malformed/duplicate or ambiguous bindings rather than coercing them into a local shape. |
| Semantic validation | Use RAES model validators, canonical digest APIs, associated-artifact validation, and reference-processor planning diagnostics. Local checks are parser resource/ambiguity hardening, cross-artifact identity joins, and explicit apparatus policy only. |
| Artifact resolution | Use the injected authorized resolver, no-follow contained opens, one-handle hash/parse, digest and size verification, aggregate limits, offline default, and no ambient lookup. No input controls imports, commands, collectors, backend methods, environment names, or filesystem roots. |
| Participant manifests | Resolve selected implementation manifests only from checksum-validated `role="manifest"` entries in the experiment's associated artifact set. Match exact parsed identity and schema to the RAES binding descriptor; reject missing or duplicate owners. |
| Secret handling | Treat the whole experiment graph as untrusted. Reject secret-shaped scalars and parameter pairs through `aptl.utils.redaction` classification before plan construction. Later redaction cannot make executable input safe. `redact()` transforms values rather than validates acceptance. Shared classification must stay in that module; callers must not copy private patterns or silently change admitted values. Keep control-plane secrets out of source artifacts and locators. |
| Config shape | Non-secret admission limits or resolver policy that become durable settings must be strict `AptlConfig` fields with real consumers. The experiment document cannot add config keys or override deployment provider/project identity. |
| Environment binding | Admission must not call `.env` hydration or construct `EnvVars`. Experiment parameters cannot name or read environment variables. Runtime secrets remain in `EnvVars`, placeholder validation, and generated config after admission succeeds. |
| Apparatus capability | Compare both task and spec constraints with canonical manifest payloads and RAES planner diagnostics. Unknown contract/capability/capture terms fail closed before `_LAB_START_STEPS`. |
| OS/process exposure | Default admission uses no subprocess. Do not put parameter values, digests used as credentials, auth headers, or artifact contents in argv, process titles, URLs, or environment. A future resolver uses in-process transport or the existing `curl_safe` boundary without credential-bearing argv. |
| Range-mutation gate | The complete plan must be admitted and persisted before `.env` hydration, key/cert generation, rendered config, volume seeding, image pulls, session creation, or any `DeploymentBackend` call. Clean boot/teardown is execution and cannot precede admission. |
| Persistence | Inject `RunStorageBackend`; reuse its configured root and shared redaction, but harden the create-once path against symlink components rather than assuming current lexical containment is sufficient. Keep plans in an explicit non-run namespace. Exporter packages already-safe run records and is never the first sanitizer. |
| Logs and telemetry | Use `get_logger`; log contract/diagnostic codes, safe identities, counts, and digests only. Raw documents, parameter values, artifact bytes, locators with queries, exception strings, and validation `input` fields never enter logs or OTel attributes. Admission spans may carry plan/trial counts and digests after `redact()`. |
| Error envelope | Normalize failures into redacted RAES `Diagnostic` values in an experiment-admission domain. Reuse the existing diagnostic formatter by parameterizing its currently hard-coded `"RAES runtime handoff failed"` prefix; do not add a second formatter or misclassify admission as a startup-readiness warning. Project only stable codes/addresses and safe messages through Typer or a future narrow authenticated API response. Do not expose raw Pydantic errors with `input_value`, YAML excerpts, absolute paths, resolver exceptions, or backend stderr. |

## Canonical incumbents

| Concern | Reuse |
| --- | --- |
| Experiment contracts and examples | `raes_contracts.experiment_spec`, exported `raes_contracts.contracts` models, associated-artifact APIs, and `raes_contracts.corpus.corpus_family_root(FIXTURES)` rather than private package-path reconstruction |
| Scenario parsing and parameter semantics | `raes.parse_sdl` over resolver-owned bytes, RAES parser limits/canonical scenario digests, and the RAES reference processor |
| Backend identity and feasibility | `create_aptl_manifest()`, `raes_backend_protocols.manifest.backend_manifest_payload`, `raes_processor.manifest.reference_processor_manifest_model`, planner diagnostics, and existing conformance tests |
| Runtime handoff | The apply/retry path already used by `start_raes_scenario()`, plus `AcesRunTarget` and `AcesStartOutcome`; `start_raes_scenario()` itself replans and therefore cannot be the admitted-plan entrypoint unchanged |
| Lab lifecycle | `_LAB_START_STEPS`, orchestration contract predicates, `LabResult`, `StartupOutcome`, and `StartupDiagnostic` |
| Deployment | `DeploymentBackend` and its typed local/SSH Compose implementations |
| Scenario containment precedent | `scenario_catalog._resolve_project_file`, strengthened to no-follow one-open semantics rather than copied into a second path checker |
| Config and secrets | `load_config`/`AptlConfig`, `EnvVars`, placeholder checks, ADR-028/029 generated-state rules, and `redact()` |
| Capture | `collectors.py`, MCP/Kali capture owners, `RuntimeSnapshot`, workflow/evaluation history, and the ADR-033/044 evidence layout |
| Persistence and export | `RunStorageBackend`/`LocalRunStore`, `RangeSnapshot.to_dict()`, ADR-044 run records, and `exporter.py` |
| Diagnostics and observability | RAES `Diagnostic`, the formatting logic in `render_raes_diagnostics()`, `get_logger`, and ADR-012 telemetry rules; `_emit_diagnostic()` remains the lifecycle-only projection when an execution failure enters lab startup |
| API exposure if added | API-wide `verify_token`, `WebAuthSettings`, BFF Host/CSRF/session middleware, existing router assembly, request-size enforcement, and narrow Pydantic response projections |

## Extensibility

The primary external extension seam is the authorized artifact resolver. It is
parameterized by trust roots/authorities, offline mode, limits, redirects,
timeouts, and digest policy while always returning the same bounded immutable
byte binding. This permits a future digest-verified OCI or registry resolver
without changing admission semantics or allowing the experiment to select a
transport implementation.

The execution-side seam is the versioned allocation/control policy and the
shared capture-capability mapping. Future ordering methods, stochastic
controls, or capture owners extend those bounded mappings. They do not edit
RAES source models, dispatch by scenario name, or add arbitrary plugin loading.

A later public RAES plan or diagnostic replaces the corresponding internal portable projection. Native resolver and storage evidence should remain in the backend journal namespace.

## Testing contract

Implementation must prove the boundary without creating a new test harness:

- RAES package fixtures cover valid and invalid authoring input, task, capture,
  associated-artifact, manifest, and scenario contracts through public APIs.
- Unit tests cover cross-artifact identity joins, apparatus/capture capability
  decisions, exact mutation ordering, redacted diagnostics, canonical bytes,
  create-once persistence, and stable IDs.
- Existing `fuzz` checks cover paths/symlinks, bounds, duplicate keys, secrets, ordering, condition counts, digests, unique IDs, and deterministic repeated admission. Run-store symlinks are included.
- Each planned trial must join exactly one task, snapshot, condition or sentinel, stochastic-control set, episode-control set, and admitted capture-reference set.
- Mutation-spy tests prove that rejected admission makes no
  `DeploymentBackend`, hydration, credential, certificate, Compose, session,
  collector, or run-execution call.

Do not weaken these tests by snapshotting APTL-local copies of RAES schemas.
The project dependency pin (`raes==2.0.0`) and `uv.lock` are the
version authority used by the fixtures and public APIs.

## Gotchas

- Pydantic validation strings can contain the rejected `input_value`; wrapping
  `str(exc)` in a diagnostic can leak an injected secret. Render only stable
  error type/location metadata and omit input values and documentation URLs.
- The locked dependency is `raes` 2.0.0, but a stale local `.venv` can
  still contain an older contract surface and fail importing the current APTL manifest. Validate
  APIs and fixtures through the locked environment; direct `python` output from
  a stale environment is not contract evidence.
- `parse_experiment_spec` is the public schema loader, but callers still need a
  byte limit and duplicate-key preflight before passing text to it. Do not use
  `load_experiment_spec` on an unbounded attacker-controlled file.
- `parse_sdl_file` and SDL import expansion reopen paths. Hashing a resolver handle before reopening the original path creates a time-of-check/time-of-use gap. Imports need an authorized staged graph or refusal.
- RAES task and capture references deliberately do not carry digest/path fields
  in their typed reference models. Pin resolved byte digests in the internal
  admission journal or a RAES associated-artifact binding; do not add forbidden
  fields or subclass the contracts.
- A generic scenario reference is not a sealed scenario snapshot. It must
  resolve to one concrete parsed/instantiated snapshot and canonical digest
  before planning trials.
- `target_runs_per_condition` and `target_run_count` have no useful apparatus
  upper bound in the portable contract. The caller policy must reject expansion
  beyond configured count/byte limits before allocating a large list.
- `allocation_method`, `replication_policy`, `stopping_rule`,
  `termination_rule`, and stochastic descriptions are data, not code. Never
  evaluate or parse them as shell, Python, templates, expressions, or import
  names.
- Current trace capture favors `.aptl/runs`, while configured CLI run storage
  can point elsewhere. Injection of one resolved `RunStorageBackend` is
  mandatory; hardcoding either root would split evidence again.
- `LocalRunStore._run_dir()` currently follows an existing run-directory
  symlink outside the configured base. The admitted-plan writer must not inherit
  that escape, and plan IDs must not be disguised as run IDs.
- `LocalRunStore.write_json` overwrites and is not canonical. Calling it twice
  is not an immutability guarantee, and bypassing it with `write_file` loses
  structural redaction.
- At the locked RAES surface, the published reference processor manifest names
  only `stub` as a compatible backend while APTL names
  `raes-reference-processor` as compatible. Local payload patches cannot manufacture apparatus compatibility. Admission refuses until canonical RAES declarations and task constraints are mutually satisfiable.
- `create_aptl_manifest().observation` is currently `None`, and the existing
  collectors are best-effort primitives that often collapse failure into an
  empty result. Do not admit a capture requirement merely because a collector
  function exists. Capture-bearing inputs need one evidence-backed shared
  capability mapping (and an honest manifest observation declaration where the
  RAES authority requires it); otherwise they fail closed.
- `render_raes_diagnostics()` currently labels every failure as a RAES runtime
  handoff failure. Reuse its formatting logic only after making the safe stage
  label explicit; do not emit misleading admission errors.
- Timestamps, absolute paths, unordered collection traversal, randomness, or UUIDs can make identities vary across hosts and retries. One apparently stable test process cannot establish determinism.
- Admission-time Docker probes would make results host-state-dependent and
  would bypass both the manifest truth surface and the no-mutation boundary.

## Non-goals

- Do not define an APTL experiment DSL or mirror RAES authoring input, task,
  capture, run, study, apparatus, evidence, protocol, or analysis schemas.
- Do not execute a trial batch, schedule workers, select participant providers,
  implement stopping rules, or perform statistical analysis as part of the
  admission slice.
- Do not redesign RAES scenario compilation, participant runtime, lab startup,
  clean boot, collectors, snapshots, run archive layout, exporter, telemetry,
  web authentication, or deployment backends.
- Do not add remote fetching by default, a plugin loader, arbitrary URI scheme
  support, or ambient package/filesystem discovery.
- Do not make the internal journal a portable RAES artifact or claim that it is
  an archival `experiment-run-v1` record.
- Do not weaken redaction so experiment parameters can preserve
  control-plane/operator secrets. Designed-vulnerable evidence remains governed
  by ADR-029 at capture time, not by the experiment input.

## Anti-patterns

- Local `ExperimentSpec`, `Task`, `CaptureSpec`, `Study`, `Run`, or protocol
  models that copy RAES fields.
- A second YAML/JSON schema validator, semantic-invariant registry, exception
  hierarchy, diagnostic DTO, readiness taxonomy, or workflow state machine.
- Resolving references after the first trial starts or reopening a path after
  hashing it.
- Letting `parse_sdl_file` or SDL import expansion bypass the authorized
  resolver after the root artifact was pinned.
- Treating a digest as optional when bytes can affect execution, or treating an
  image tag/path/URI as immutable identity.
- Passing input strings to `getattr`, `importlib`, `subprocess`, shell, Docker,
  collector dispatch, environment lookup, or backend method selection.
- Letting condition names or scenario IDs select behavior in `if`/`match`
  branches instead of using typed RAES fields and bounded policy mappings.
- Logging raw validation/resolver exceptions or returning them through CLI/API
  error envelopes.
- Replanning a trial at execution time and accepting a plan that differs from
  the persisted digest.
- Storing a plan as a synthetic run, adding a fake run manifest, or silently
  redacting identity-bearing plan values during persistence.
- Using exporter filtering, file permissions, `.gitignore`, or an offline flag
  as a substitute for admission-time containment, authorization, and redaction.

## References

- EXP-002 / GitHub issue #438.
- [ADR-025](adr-025-strict-first-party-config-schema.md): strict APTL config.
- [ADR-029](adr-029-control-plane-secret-handling.md): secret classification
  and serialization-boundary redaction.
- [ADR-031](adr-031-lab-orchestration-contract-guards.md): lifecycle guards and
  existing error envelopes.
- [ADR-035](adr-035-raes-sdl-adoption.md): RAES contract authority and adapter
  boundary.
- [ADR-039](adr-039-web-control-plane-authentication.md): API auth and error
  exposure.
- [ADR-044](adr-044-raes-aligned-run-reproducibility-record.md): portable RAES
  identity versus APTL backend evidence.
- [ADR-046](adr-046-dynamic-raes-scenario-realization.md): compiled-plan
  authority, manifest capability gates, and `DeploymentBackend` realization.
