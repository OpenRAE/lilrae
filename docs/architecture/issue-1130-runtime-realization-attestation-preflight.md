# Issue #1130 Runtime Realization Attestation Preflight

Issue #1130, including folded-in #1128, is the single delivery contract and PR.
Child attribution, receipts, supervision, and teardown are in scope alongside
runtime reporting. This note records architecture boundaries, not an
implementation plan. Reuse [ADR-046](../adrs/adr-046-dynamic-raes-scenario-realization.md)
for realization and SEM-218, [ADR-044](../adrs/adr-044-raes-aligned-run-reproducibility-record.md)
for run records, and the [#964 ownership](issue-964-backend-resource-ownership-preflight.md),
[#974 orchestration](issue-974-shuffle-worker-docker-images-preflight.md), and
[#992 observability](issue-992-backend-observability-ownership-preflight.md)
boundaries. ADR-055 remains proposed; this note does not accept its policy model.

## Current Contract And Design Constraint

The initial preflight assessed `raes==7.0.0`.
The working branch now pins RAES 9.2.0 and environment-packs 6.5.0 on Python 3.14.
The lock, generated requirements, and installed distributions match those pins.
Delivery uses the public descendant contract introduced in RAES 8.1.0, specified by
[OpenRAE/rae#1649](https://github.com/OpenRAE/rae/issues/1649) and
[OpenRAE/rae#1651](https://github.com/OpenRAE/rae/issues/1651). This supersedes the
earlier preflight's wait-for-upstream prerequisite. Consume public released
contracts and their validators; do not copy schemas, patch dependencies, edit
another checkout, or add an APTL compatibility bypass. Keep the pin, lock,
generated `requirements/*.txt`, installed-wheel checks, and appliance wheelhouse
consistent through the existing `.pre-commit-ci.yaml` lock/export hooks.

The issue's zero-constructor measurement does not mean provenance is absent:
`raes.py::_apply_execution_plan()` delegates to
RAES `RuntimeManager.apply()`, which validates realization and attaches
`RealizationProvenanceEntry`. Existing tests in `tests/test_raes_backend.py`
exercise author-declared, processor-derived, and backend-realized origins.
All three focused provenance tests passed during this preflight.

The remaining boundary is broader than constructing another ledger entry:

- `raes_observation.observe_realization()` and
  `raes_diagnostics.snapshot_after_apply()` enumerate planned resources.
  `_raes_operational_observation.py` additionally requires matching operation
  and envelope identity. Preserve that binding; removing it permits stale proof.
- RAES entry/effect transition validators protect membership and runtime-owned
  provenance, metadata, and materialization archives. A syntactically valid
  address does not authorize adding an entry. Submit descendants through the
  8.1.0 contract and prove acceptance through `RuntimeManager`, including
  subsequent observations and the final returned snapshot.
- The existing materialization description/archive contracts and
  `MaterializationOrigin` are separate from native causation and the SEM-218
  ledger. Reuse them only where the released descendant contract requires
  them; descriptive SDL is neither a discovery algorithm nor permission to
  execute it. Do not require prospective SDL to predict arbitrary children.

The primary session subsequently inspected the released 8.1.0 documentation
and installed wheel in an isolated temporary environment. All 41 selected
upstream descendant, provenance, admission, durability, bounds, and contract
checks passed. The public producer interface is
`refresh_inventory(request, predecessor)`; the manager entry point is
`RuntimeManager.refresh_inventory()`. Both descendant and materialization
attestation contracts must be negotiated, with a runtime-owned archive.
These checks establish the upstream reporting path, not native child causation.
The [reporting design](issue-1130-owned-descendant-reporting-design.md) records
the integration boundary and the maintainer's decision to retain the existing
shared daemon unchanged. The maintainer subsequently selected "just record":
cooperative socket recording without a new enforcement policy. This accepted
trust limit supersedes any requirement below to prevent a hostile raw-authority
holder from bypassing recording. Known gaps remain visible; unrecorded candidates
never gain cleanup authority. The design records the complete selected boundary.

## Identity, Responsibility, And Evidence

Keep these concepts distinct:

| Concept | Required boundary |
| --- | --- |
| Desired resources | The original compiled plan and authored SDL remain unchanged. `realized_children` is authoring input, never the backend output channel, ownership proof, or expected inventory. |
| Observed resources | Public RAES addressing and admitted collection semantics identify every reported addition, including backend apparatus and transitive descendants. Preserve an explicit link to the responsible holder/ancestor and run/operation; never attribute another resource's facts to the holder's address. |
| Native ownership | `WorkspaceOwnership`, `ResourceReceipt`, and `ComposeResourceResolutionMixin` bind workspace, effective project, daemon, attempt, and native ID. A receipt's `node_address` may identify the parent; it is not a unique child runtime address. |
| Provenance | SEM-218 explicitness describes the concern's governing constraint; origin describes who supplied its realized value. Observation strength describes the evidence. None establishes ownership or grants authority. |
| Materialization description | The RAES descriptive SDL and archive reference report the realized world. They neither replace the authored scenario nor grant permission to execute that description. |

#1128's identification, ownership, and lifecycle work is part of this delivery.
The RAES adapter consumes backend causation evidence; it must not create a
second discovery or ownership mechanism. Responsibility extends
through delegation regardless of spawn depth, template match, or whether the
resource is a planned node. Responsibility does not permit inspecting unrelated
containers. Labels, names, image equality, timestamps, and daemon-wide lists
cannot prove causation; a raw-socket holder can forge ordinary Docker labels.
Do not silently claim a complete inventory when attribution is unavailable.
Reporting an unexpected descendant must preserve the observed deviation; it
does not make that resource authorized. Reuse RAES augmentation-scope admission
for backend additions such as apparatus, preserving closed/exact scopes and
independent operator policy. Do not require authors to predict children or
widen a scope merely to make the attestation validate.

## Native Attribution And Child Lifecycle

Native causation is LilRAE's responsibility; RAES admitting a descendant does
not prove who created it. Ordinary Docker inspect/event metadata does not
establish a caller-to-create relationship. A Docker-created container is a
sibling daemon object, not proof of an OS process child of its holder. Namespace
joins, event order, images, timestamps, names, and ordinary labels cannot
distinguish two concurrent attempts. Socket holders can forge labels and create
objects with arbitrary mounts: [Docker's daemon security boundary](https://docs.docker.com/engine/security/)
is relevant here. Do not add an image/label heuristic with a provenance name.

The existing isolation route is an acceptable attribution boundary only when
the provider proves exclusive control of the daemon for the attempt and
responsible authority chain, accounts for controller-created objects, and
records new native IDs durably. Two such isolated runtimes can share a physical
host; sharing one daemon is a different claim. Per-seat guest isolation and the
in-memory `_attempt_isolated_docker_daemon` flag alone prove neither current
attempt exclusivity nor an immediate parent. Multiple holders require causal
evidence distinguishing their authority chains; do not guess a parent. On a
shared daemon, support requires native create-call attribution that binds the
verified caller/authority to the daemon-issued created ID. No such collector
exists in this checkout. An events-only observer is not that collector.

This is a proof boundary, not authorization to launch another daemon, proxy,
service, or host instrumentation, or silently redirect the selected endpoint.
Record the concrete method and its trust assumptions before claiming support.
If causation cannot be established, emit bounded ambiguity diagnostics and
perform no mutation on those candidates. That safe failure alone does not
fulfill the positive descendant acceptance criteria.

Collection must begin before authority delegation and retain create/remove
evidence for short-lived descendants. Polling only surviving containers misses
autoremove and between-poll lifetimes. A lost event window, collector outage,
or unreadable create result invalidates completeness; it cannot become a clean
empty inventory. Preserve verified cleanup authority and report the gap.

Build on these existing owners:

| Incumbent | Guardrail for this delivery |
| --- | --- |
| `WorkspaceOwnership`, `ResourceReceipt`, `ComposeResourceResolutionMixin` | Record every verified child with `managed_by="child"`, full native ID, workspace/project/daemon/attempt, and durable authority lineage before observation or lifecycle action. Extend the existing versioned lifecycle record only if needed; old records without proof cannot gain authority through defaults. Revalidate the exact receipt and chain before each action. A child's receipt `node_address` currently names its holder, not its unique runtime identity. |
| `_record_isolated_child_receipts()` | This unused helper assumes isolation and takes an image requirement. It is not a collector or causal proof. Attribution must work without a template/image match and transitively when a child receives daemon authority. Preserve every native ID; one template can produce many children. Do not feed child template names into `_add_receipted_container_names()` as one-to-one planned-node mappings. |
| `DeploymentDockerAuthorityAdmission`, `raes_runtime_orchestration.py`, `docker_authority_admissions()` | Carry the authored lifecycle timeout with the responsible authority independently of `DeploymentSpawnImageRequirement`. The current timeout is carried only through non-empty image templates; an empty template list must not disable child supervision. Reuse same-node reference, authority integrity, and positive finite timeout validation. |
| `lab.py::_supervise_started_lab()`, lifecycle observation/mutation locks, backend `verify_runtime_orchestration()` | Reuse lifecycle coordination; do not add a second workflow engine or a detached timer per child. A final readback cannot enforce a live deadline. Establish supervision while authority can create children, with cancellation/recovery ownership. Honor the released lifecycle's deadline anchor/scope explicitly, using an absolute monotonic deadline during execution. Rediscovery/retry must not restart it, and delegated children must not extend a governing ancestor deadline. Persist trusted timing context for recovery without treating a process-local monotonic value as a wall clock. |
| `_compose_project_cleanup.py`, `_compose_stop.py`, `_compose_lifecycle.py`, rollback and autoremove | Current stop/kill paths select `direct` and `compose`, and label-based residual checks miss unlabelled children. Include verified `child` receipts in normal stop, failed-start rollback, clean boot/reset, emergency stop, and recovery; remove children regardless of `-v`. Quiesce authority producers and drain descendant discovery before declaring cleanup complete, so teardown cannot race a new child. Prove absence by native ID and retain uncertain/residual receipts. |

Receipt authority is not refreshed by a label match. A separately admitted
start gets a new attempt; retry within the same admitted start retains its
identity and recorded causation without resetting deadlines or duplicating
receipts. Exact-attempt observation/supervision rejects stale prior-attempt
receipts; explicit workspace recovery can clean older verified owned resources.
The retry owner already closes the failed `RuntimeManager` before replacement
(#1424); supervisors must not survive that ownership boundary and act later.

Deadline coordination must also work while the admitted start owns the project
lock and waits for workflows. The selected design treats the recorder as that
start's child operation. Teardown keeps the existing project owner and drains
the recorder's creation and deadline actions before child cleanup. Reacquiring
the parent's exclusive lock in the child would prevent live timeout enforcement.
This refines the coordination guidance above; it grants no general mutation
path outside the recorded attempt and does not introduce another workflow engine.

Provider reads and actions belong behind `DeploymentBackend` /
`ContainerOpsBackend` (`backend_container_ops.py`) and the shared Docker/SSH
runner. Keep receipt resolution central, revalidate the selected endpoint, and
use the verified ID throughout. Do not re-resolve names after validation or
treat a fresh daemon-ID response as proof that a failed container inspect means
absence. Inspection failure during supervision is an observable failure, with
no action on an unverified candidate, and does not abandon the remaining
verified resources. Mutable ownership state stays outside sealed run evidence.

## Provenance And Observation Semantics

RAES remains the classifier, concern registry, validator, and ledger owner.
Reuse compiled authority/requirements, `ExplicitnessClass`,
`ExplicitnessProvenance`, `CONCERN_PAYLOAD_PATH`, and
`project_realization_concern()`. Preserve authored and processor-derived origin
when the backend honors their values; use backend-realized for an admitted
backend selection. Equality alone cannot reconstruct origin, and constrained
does not necessarily mean backend-realized. An authored template can account
for an inherited field only through upstream compiler lineage, without making
a child's existence author-declared.
Do not classify an entire container uniformly or mark every concern open.
The three existing provenance tests establish planned-resource behavior only;
descendant provenance still needs proof through the 8.1.0 runtime path.

`RealizationProvenanceEntry` contains references and classification, never
realized values. Value-bearing observations use existing concern projectors
and `_runtime_concern_disclosure._disclose()`; `_record()` handles bounded
readback failures. `MaterializationOrigin` describes differences and is not a
replacement SEM-218 ledger. Missing evidence stays missing and required
evidence fails closed; planned values, successful commands, image tags, and
manifest capability declarations are not runtime proof.

Preserve operation ID, envelope/configuration digests, observer version,
sequence, and verified binding where the RAES contract requires them. Run ID,
attempt ID, operation ID, semantic address, and native ID are different joins.
Use the canonical disclosure identity
`(address, field_path, domain, requirement_kind)` and the existing delta-only
return convention: the runtime appends operational disclosures. Do not append
the same disclosure through both snapshot assembly and `ApplyResult`.

Attestation must name its observation boundary. Initial apply precedes workflow
execution in `raes.py`; it cannot observe children spawned later. Later
readback must use the released descendant operation and preserve predecessor
lineage. Reuse the existing start/orchestrator lifecycle; evaluator-only evidence
refresh is a separate phase, not permission to mutate provisioned membership.
The snapshot returned in `AcesStartOutcome` and persisted by `raes_repro` must
include the accepted later readback, rather than retain the pre-workflow copy.
Do not mutate manager internals or create another workflow engine.
Retain bounded evidence before autoremove through `DeploymentObservationContext`
and `CompletedContainerReceipt`; an absent child cannot be reconstructed from
its template. Distinguish observed termination, incomplete collection, and
failed observation. Bound collection time, resource count, depth, and bytes;
cycles, overflow, or interruption must disclose incompleteness, never truncate
silently or erase cleanup receipts. Preserve prior witnessed children when a
later inventory is incomplete; report terminated, removed, and unobservable
state using the released contract rather than silently deleting history. The
bounded reporting window is distinct from live child deadline enforcement.

## Coverage Assessment Beyond The Three Operational Binders

The operational binder is one channel, not the total observation coverage.
Existing observers already cover networks, content, generated artifacts,
volumes, and many runtime concerns. The realization envelope advertises more
concerns than those three binders; neither it nor backend details proves
per-operation coverage. Extend existing observations where state is held and
public contracts permit it; keep unsupported/unobserved dimensions explicit.

| State to account for | Canonical incumbents and guardrail |
| --- | --- |
| Added containers, descendants, capture apparatus, operator-access relays, temporary provider helpers | Folded-in child ownership; `_raes_apply_reporting.capture_apparatus_observations()`, `_compose_observability.py`, operator-access helpers, and `ephemeral_containers.py` already hold evidence. Their detail-only addresses or helper names are not admitted RAES membership. Include additions without inventing authored nodes or enabling apparatus just to observe it; disclose missing evidence for helpers that have already disappeared. |
| Networks, attachments, host publications, listeners, ACLs | `_raes_network_observation.py`, `_raes_runtime_network_observation.py`, network realization readback, `raes_acl_realization.py`, and backend ACL verification. Preserve separate network, container endpoint, and host exposure facts; a requested rule is not an observed rule. |
| Image, platform, OS, limits, privileges, namespaces, lifecycle | `_docker_image_identity.py`, `_raes_guest_os_observation.py`, `_raes_guest_process_limits.py`, `_raes_runtime_container_observation.py`, and substrate attestation. Preserve immutable image identity versus alias and daemon versus guest evidence. Do not apply an APTL service's containment assertion to every arbitrary child. |
| Content, artifacts, certificates, volumes, accounts | `_raes_stateful_observation.py`, artifact/content satisfaction and delivery observers, account verification, and service-index readback. Report identities, delivery, and verified state using existing typed models; no content bytes, private keys, account secrets, or generic file crawler. |
| Environment, mounts, service/application state | `_raes_runtime_environment_observation.py`, `_runtime_mount_observation.py`, guest inventory readers, service health, and forwarding-agent readback. Retain secret classifications and actual evidence strength. `raes_runtime_attestation.py` is a content-pinned compatibility bridge, not a general application observer. |

Child-created networks/volumes need the same causal proof before ownership;
attachment to an owned container alone does not authorize inspecting or
removing a shared resource. Preserve existing volume-retention semantics.

## Cross-Cutting Layers The Design Must Pass

| Layer and canonical incumbent | Required passage |
| --- | --- |
| Caller authentication: `api/deps.py::verify_token`, BFF Host/CSRF/session gates | Retain authenticated lifecycle access. Add no route, token, listener, client-supplied ownership, or grant. Runtime reporting does not authorize Docker use. |
| Shape, identity, authority: released RAES 8.1.0 descendant contract, parser/compiler, `require_compiled_address`, snapshot/transition validators, observation binders, manifest and realization envelope | Use typed public contracts, canonical addressing, admitted membership, unique concern keys, portable value limits, and matching operation/envelope identity. Descendants need stable distinct addresses, not a holder's address or a backend string grammar. A successful dataclass constructor is insufficient; prove acceptance through `RuntimeManager`. Advertise only delivered capabilities. |
| Local policy/config: strict `AptlConfig`/`DeploymentConfig`, project-name validator, signed `ApplianceBoundaryPolicy`/`DockerAuthorityPolicy`, effective Compose and substrate gates | Reporting needs no new config switch, policy grant, or scenario field. Preserve existing holder admission and containment for services APTL lowers. #1129 owns future operator-grant changes; do not widen access to make reporting easier. |
| Provider and native ownership: `DockerEndpointBindingMixin`, `WorkspaceOwnership`/`ResourceReceipt` validation, `ComposeResourceResolutionMixin`, SSH backend transport | Revalidate selected socket/daemon, durable causation chain, and exact-attempt native handles. An SSH route must honor its existing capability limits rather than accidentally inspect the controller's local daemon. Receipt/schema failures, endpoint swaps, foreign state, and uncertain causation produce bounded failures, not adoption. |
| Environment and credentials: `_environment_bindings.py`, `_compose_environment.py`, `_realization_primitives.py`, account credential projections | Reuse declared source/grant shapes and env-file validation. Observation must not bind new values or read ambient secrets. Protected variables are presence-only; preserve withholding of externally supplied `secret_fixture` commitments, whose unsalted hashes permit guessing. An arbitrary child's unclassified environment, command, labels, mounts, and files are untrusted and potentially secret: project allowlisted facts, never dump inspect. Credential-bearing plans retain `closed_credential_result()` and the upstream credential-result sanitizer. |
| Host/OS exposure: backend `_run()`/`_subprocess_kwargs()`/`_run_with_input()` and existing file delivery | Fixed argv lists, validated full native IDs, bounded collection/reads/timeouts, contained owner-only files, and pinned transport. The current captured subprocess runner alone does not impose a byte cap. No secret in process argv, arbitrary shell fragments, extra mount/capability, registry lookup, or network transfer. Preserve loopback publication and offline behavior. |
| Errors/logs: `BackendObservationError`, `BackendTimeoutError`, `OwnershipConflictError`, RAES `Diagnostic`, `LabResult`, `get_logger()`, redaction | Distinguish valid empty results from failed collection. Emit bounded reason, stage, and safe identity; no raw inspect/env/config, stdout/stderr, traceback values, or workflow payload. `get_logger()` does not automatically redact. Reuse failure-diagnostic preservation; add no exception hierarchy or blanket retry. |
| Persistence and visibility: `pathsafe`, lifecycle receipts, `raes_repro.runtime_snapshot_record_payload()`, `LocalRunStore`, `core/archival/seal.py` | Keep mutable ownership state out of sealed evidence; serialize runtime provenance through its public snapshot projection, separately from `RangeSnapshot` and REP-003 provenance. Persist final accepted descendants before sealing. `write_json()` redacts; `write_file()` does not. If materialization SDL is required, adapt the public archive protocol to existing protected local storage and validate exact immutable bytes/digests before publishing references. Retain source/run lineage. Participant projections must not expose the operator's complete inventory, evaluator state, protected SDL, or native host paths. |

Materialization semantic identity and stored-byte checksum are separate checks.
Do not hash an artifact and then redact or rewrite its bytes; use the existing
protected artifact boundary and verify the exact published content.

## Extensibility And Verification Boundaries

The seam belongs between backend-owned causation, inventory/readback and RAES's
admitted addressed realization, parameterized by resource kind, native identity,
responsible parent/authority, workspace/daemon/attempt, run/operation, governing
scope, concern, evidence strength, and bounded observation window. Extend the
existing deployment observation context and public runtime contracts as
needed; do not introduce a generic attestation framework or second registry.
A second-generation child, a non-container backend, or a capture relay must
fit the same mapping without a Shuffle/TechVault name branch or new address
grammar. Source a concern catalog from RAES rather than copying its schema.

Focused tests must demonstrate a descendant absent from the original plan
reaching the accepted runtime output, including a grandchild and a child born
after initial apply. Prove two concurrent attempts with identical child images
cannot cross-adopt, observe, stop, or remove each other's children. Cover retry,
stale prior-attempt receipts, and inspection failure during supervision, plus
daemon swaps, replacement, autoremove, missing evidence, duplicate disclosures,
limits, repeated readback, and interruption/recovery. Verify timeout enforcement
with an injected clock, no deadline reset, template-free/unknown-image children,
and teardown racing a holder's final spawn. Assert all verified children are
removed and every foreign/ambiguous candidate is unchanged. Assert both
explicitness and origin for the three provenance cases,
including an admitted backend choice within a constrained domain. Use secret
canaries across snapshots, details, diagnostics, logs, archive projections,
and process argv. Reuse `test_raes_backend.py`, `test_raes_observation.py`,
`test_compose_resource_ownership.py`, `test_raes_runtime_orchestration.py`,
`test_cli_lifecycle.py`, `test_raes_repro.py`, and their fake backends. Native
integration tests must exercise the chosen attribution method on a shared host
with concurrent attempts; a mock or a single isolated daemon cannot prove that
boundary. Verify final snapshot serialization and participant non-disclosure,
not just a backend method's intermediate result.

Whole-repository scope includes the dependency pins, canonical manifest/envelope,
RAES admission/provisioner/manager, Docker and SSH protocols and runners,
lifecycle ownership/recovery, workload execution timing, capture/operator
apparatus, environment/config/secret gates, API/CLI errors, snapshot/run-store
projections, and archive finalization. Keep `.ground-control.yaml`,
`.gc/plan-rules.md`, `tools/run-targeted-tests.sh`, `.pre-commit-config.yaml`,
`.pre-commit-ci.yaml`, `mkdocs.yml`, and `.github/workflows/checks.yml`
authoritative: targeted tests and staged hygiene locally;
full suites, whole-tree prose checks, coverage, and clean lab lifecycle in CI.
This requirement-free issue creates no requirement UID or status transition.

Non-goals are #974's image-list and `realized_children` conceptual fixes,
#1129's independent operator-grant policy, host-wide process surveillance,
scenario success semantics, or an archival, logging, exception, DTO, or workflow
replacement. Do not use `ApplyResult.details`,
snapshot metadata, REP-003 records, or materialization references as a substitute
for accepted addressed runtime output and its SEM-218 ledger. This preflight
changes guidance only and makes no delivery claim for #1130. Both child
ownership/lifecycle and runtime reporting must ship in the existing #1130 PR;
#1128 remains open until that delivery merges. No other checkout changes,
service deployment, dependency bump, implementation, or issue closure occurs
in this preflight. Preserve existing `aptl` interface identifiers and apply
ADR-062's LilRAE naming only to new identifiers; do not create aliases.


## Released dependency qualification

The published `raes-env-packs` 6.4.1 package requires `raes==8.1.0`.
The ordinary resolver accepts those pins without overrides.
That pair cleared the original release dependency.
The current lock and generated exports select the later compatible pair below.

RAES 8.1.0 target conformance rejects a negotiated reporting target before apply.
The diagnostic is `materialization.source-context-required`.
The runner omits the required run scope and protected archive owner.
The public runner options expose neither input.
[RAES issue 1667](https://github.com/OpenRAE/rae/issues/1667) records a standalone reproduction.
Only an issue was created upstream; no upstream source or checkout was changed.
RAES 9.1.0, published on October 28, 2026, includes that repair.
The released wheel's probe owner now supplies both the run scope and a protected archive.
The release therefore supplies the missing runner behavior.
Removing contract declarations or suppressing that probe would weaken qualification.

Environment-packs 6.4.2 now requires RAES 9.1.0.
The released pair clears the earlier exact-pin conflict.
The maintainer authorized the dependency and Python upgrade on 29 October.
Both packages require Python `>=3.14,<3.15`.
The application, CI, release jobs, and generated dependency exports must use that range.

RAES now owns the full run through one `RuntimeControlPlane` instance.
Its `RuntimeManager` export names that same class.
Use the public `evaluate()` method for later evidence.
Keep participant delivery on the same owner with constructor-bound policy and behavior specifications.
Remove the private claim handoff and snapshot adoption paths.
The owned descendant design records this migration.

Both bundled TechVault packs now use version 0.1.3.
Their artifact bytes remain unchanged; artifact versions and the MISP declaration change.
MISP 2.5.50 requires the new immutable backend profile.
The RAES 9.1 projections also add empty default fields to five attested concerns.
The consumer updates the exact content identities and projection hashes after checking those differences.
The configured guest base and application containers already use Python 3.14.

The released runner now passes all three targeted backend conformance profiles.
A separate provenance regression exposed a defect in RAES 9.1.0.
That release accepts a first-party resource through public preparation without emitting its SEM-218 ledger entries.
[RAES issue 1697](https://github.com/OpenRAE/rae/issues/1697) contains a standalone reproduction using bundled stubs.
The reproduction's capture container appears in the accepted snapshot and protected SDL, but lacks per-concern backend provenance.
The backend cannot write that runtime-owned ledger or invent delegated-holder causation.
RAES 9.2.0, published on October 29, 2026, includes the correction.
The standalone bundled-stub reproduction now records provenance for both original and prepared switches.
The released wheel matches SHA-256 `7f5562544d3d87c99f1cae436c4bff8a01636a6641d35a45c106af347181992a`.
Its release tag includes the fixing commit from PR 1703.

Environment-packs 6.4.2 required exactly RAES 9.1.0 and prevented adoption.
[Environment-packs issue 525](https://github.com/OpenRAE/env-packs/issues/525) records that conflict.
Environment-packs 6.5.0, published on October 29, 2026, supports RAES 9.2.0.
The ordinary resolver installs the released pair without package overrides or dependency edits.
The consumer's capture provenance regression now passes through the public runtime.
The capture entry and its protected SDL retain runtime-owned backend provenance.
Targeted pack qualification retains both existing exact 0.1.3 content identities.

The current development base uses `ScenarioAdmissionSource` for preselected inputs.
The planning options live in `_raes_planning_entry.py`.
Reporting must preserve these interfaces and sealed family trial identities.
The single runtime owner retains the reporting archive throughout every phase.
Compose feature admission must precede recorder startup.
