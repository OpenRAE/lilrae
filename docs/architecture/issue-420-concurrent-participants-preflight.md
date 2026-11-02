# Issue #420: Concurrent Participants Through RAES

## Contract and decision

Issue #420 requires a scenario to execute autonomous red and blue
participants concurrently, preserve their authority and ordering, specify
failure/timeout/cancellation effects, and truthfully declare the capability.
Its supplied issue body is authoritative. The withdrawn AGT-002 requirement
and the historical readiness review do not override this reopened scope.

Extend the existing RAES participant adapter and runtime target. RAES owns
participant meaning, scheduling, admission, shared time, lifecycle, and
serialized state settlement; LilRAE owns bounded native execution, provider
processes, concrete target binding, and evidence publication. No new ADR is
needed: this preserves ADR-035/046, the secret boundary in ADR-029, and the
terminal-attempt boundary in ADR-050. This note is design guidance, not an
implementation plan or a claim that concurrency is qualified.

Inspection used this repository and its installed `raes==7.0.0`, matching
`pyproject.toml`, `requirements/runtime.txt`, and the installed package metadata.
The RPT scenario is not present in the inspected source/scenario files. Its
exact policy, actions, targets, observation boundaries, and implementation
bindings must come from the adopted scenario and #419 integration contract;
do not guess them from the words red and blue.

Follow-up inspection found the local RPT `techvault-purpleteam` pack at
version `0.1.2`. Its `sdl/techvault-purpleteam.sdl.yaml` defines the environment,
red/blue interactive SSH access, and a Cortex enrichment observation boundary.
It contains no autonomous execution policies or action contracts.
This release cannot supply the required autonomous bindings.
Use a representative authored scenario to qualify the backend now.
Final RPT qualification requires its eventual authored bindings.
The user approved this distinction and expanded scope to harness and prompt variation.
The listed upstream dependencies, `OpenRAE/rae#304` and `#1439`, are closed;
their issue status is not the remaining design input.

The existing [public family adapter contract](../reference/family-adapters.md)
already assigns RPT its TechVault-family implementation and qualification.
Reuse `FamilyTrialInput`, `AdmittedFamilyTrial`, and `QualifiedFamilyTarget`
in `scenario_family.py`: exact pack release, family digest, backend identity,
sealed plan entry, and one compatible installed distribution across the six
existing adapter groups. Bundled TechVault qualification is not RPT
qualification. Keep RPT-specific native facts behind those adapters, using
their scoped operations; do not give extensions an unrestricted backend,
project path, run store, or peer credentials to implement coordination.

## Existing mechanisms and boundaries

- `AptlParticipantRuntime` already inherits
  `BaseParticipantRuntime.admit_actions_concurrently()` through RAES's
  `ParticipantExecutionRuntimeMixin`. It gives workers separate deep copies of
  the predecessor, bounds overlap, and returns results in request order.
  Reuse it where its behavior satisfies the admitted execution policy. Do not
  introduce another executor merely because no batch method appears locally.
- The missing local autonomous seam is `bind_autonomous_action()` from
  `AutonomousParticipantRuntime`. Bounded overlap and execution lifecycle
  methods are described by `ControlledAutonomousParticipantRuntime`.
  Inherited batch execution alone does not establish either full conformance
  or safe native cancellation. Runtime registration checks callable signatures
  as well as capability declarations.
- RAES `ParticipantScheduler` owns due actions, reservations, temporal
  assessment, ordered settlement, conflicts, and generation fencing. Its
  concurrent dispatch/commit/settlement modules explain the pinned behavior;
  they are not modules to copy or new private integration points to import.
  Execute through the existing manager/control-plane path, not by calling the
  batch helper as an alternate top-level workflow.
- Preserve one live owner of the target. `AptlRuntimeManager`,
  `LilraeRuntimeHandoffMixin.control_plane()`, and RAES `RuntimeResourceClaim`
  already coordinate ownership. The scoped handoff drains the manager and
  pauses its clock driver; a control plane per participant would defeat both
  ownership and autonomous progress. See
  [the runtime handoff decision](issue-1447-runtime-owner-handoff.md).
- The bounded provider path (`run_participant_turn()`, apparatus projection,
  selection parsing, v2 binding, native realization) and sequential inject
  delivery (`_ParticipantDeliveryExecutor`) are distinct existing mechanisms.
  Parallelizing inject turns, launching two CLI processes, or advertising
  multiple supported roles does not satisfy autonomous action admission.
  RAES 7 autonomous selection strategies are `ordered_cycle` and `weighted`;
  neither means provider-selected v2 proposals. Preserve exact delivered-view
  binding if #419 supplies a decision provider; do not invent an `llm` strategy
  or pass provider text directly to native execution.

## Ordering, isolation, and terminal behavior

Workers execute against isolated copies of one admitted predecessor. Return
exactly one typed `ParticipantActionApplyResult` per submitted request, in
request order, with matching participant, episode, action instance, scope,
generation, and temporal coordinates. RAES validates and merges those results
serially. Worker finish order is not semantic order. Snapshot isolation does
not make simultaneous mutations of the same native service serializable:
admit overlapping targets only where the existing native operation and authored
policy support them, and verify actual effects by readback.

| Event | Required effect on peers and trial |
| --- | --- |
| Binding, shape, authority, capacity, or snapshot isolation rejection before dispatch | No native action starts; retain the RAES rejection and predecessor. Never silently downgrade a requested concurrent run to sequential execution. |
| Known action failure or timeout with a valid terminal result | Preserve all already dispatched peers' results. RAES settles the batch before honoring the authored failure policy. `stop` stops subsequent governed progress; continuation is allowed only by the admitted policy. A participant failure is not automatically an infrastructure failure or successful trial. |
| Participant-scoped cancellation | Use the admitted RAES execution scope and lifecycle action. Stop new work in that scope, bound/drain owned native work, and fence late completions. Preserve peers outside that scope; a shared service scope can affect both participants and must be declared as such. Do not claim participant-local cancellation using a scope-wide stop. |
| Trial cancellation | Stop new work across the trial's scopes, settle/drain owned work, retain partial evidence, and return the existing `TrialTerminalSignal.CANCELLED` through the trial owner. Never reset or seal while workers can still mutate the trial. |
| Raised/cancelled batch call, missing/extra results, or unpairable outcomes after dispatch | RAES treats submitted work as indeterminate; native effects may already exist. Retain its settlement and non-retryable identities. No rollback claim, fresh action IDs for blind retry, or fabricated success. |
| Generation change, invalid result, or merge conflict | Let RAES reject/settle the result; a late native completion cannot restore an old episode or overwrite a newer state. Record native evidence separately from accepted portable state. |
| Evidence publication or required capture failure | Preserve accepted RAES state and diagnose publication separately. Required evidence loss affects trial validity through the evidence coordinator; it cannot be hidden by successful peer actions. |

Use the existing `ExperimentExecutor` workload seam, `TrialOutcome`,
`normalize_terminal_cause()`, `acquire_evidence()`, and
`finalize_terminal_attempt()` for experiment trials. Map an authored stop to
the existing policy-stop signal, a scenario failure to scenario-failure, and
indeterminate infrastructure work to interruption; required capture loss keeps
its existing precedence. Scenario startup remains under its existing startup
failure owner. Do not create another trial state machine or seal per participant.

Cancellation needs native proof. Cancelling a future does not interrupt a
running worker. RAES's inherited thread pool waits for submitted work; a raised
worker can make the batch result indeterminate. At initial inspection,
`BoundedProcessRunner` cleaned up on interruption or timeout, but had no public
cross-thread cancellation handle. This change adds a per-invocation event.
Its process-group cleanup does not terminate
escaped descendants or prove a remote Docker/SSH command has stopped. Bound
those operations at their actual execution boundary, report residual work, and
do not promise immediate cancellation or rollback. Logical scenario time,
provider wall-clock deadlines, and cleanup grace periods are distinct budgets.
Use measured timeout inputs and existing caps; do not multiply an unbounded
provider workload by the participant count.

## Cross-cutting security and validation passage

| Layer and canonical incumbent | Required passage |
| --- | --- |
| Scenario/plan and capability admission: RAES parser/compiler, `ParticipantPlanAuthority`, `create_runtime_target()`, `raes_planning_compat.py` | Consume the admitted model and run-selected implementation. Preserve source/model identity and reject unavailable realizations before launch. Do not loosen the frozen bounded-agency scenario digest to make RPT fit its privileged registry. |
| Family and extension admission: `scenario_family.py`, existing six provider entry-point groups, `scenario_verification.py` | Retain atomic family/release/backend qualification and pinned provider installation identity. Pass detached admitted scenario data and bounded operations. Reject missing/mixed providers before preparation; neither matching role names nor bundled legacy providers authorize RPT family behavior. |
| Manifest: `raes_manifest.py`, `_raes_participant_manifest.py`, RAES `ParticipantRuntimeCapabilities`, `BackendManifestV2Model`, capability-gap checks and registry validation | Declare autonomous feature/flag agreement, supported policy/selection profiles, exact action/boundary/target sets, relational `execution_bindings`, finite participant/action/occurrence/retry/burst/in-flight limits, bounded concurrency and its capacity. Include required contract versions, compatible time capability, and only implemented lifecycle actions; v3 also requires resource-budget capabilities. Pass both Python capability and serialized manifest validation, then plan admission and runtime registration. A generic `multi_participant=true` flag is not the contract. |
| Participant authority: RAES control-plane identities, `ParticipantControlSubjectBinding`, control intents and crossing mediation | Bind each controller to its participant and target, with the existing policy revision, expected state revision, provenance, evidence and idempotency coordinates. Never share elevated controller authority between red and blue. The inject-specific crossing resolver and its permits are not a generic autonomous authorization bypass. |
| Visibility and hostile decisions: `raes_participant_apparatus.py`, projection/exposure modules, `parse_provider_selection()`, RAES v2 binder | Keep participant views, candidate aliases, observations and provider handles scoped to the exact participant/episode/delivery. Reuse bounded parsing and exact candidate membership. Do not expose evaluator records, peer private context, or backend handles. Stale selections require the existing admission decision, not reconstruction against a newer view. |
| Config and environment: `AptlConfig`, `InstalledParticipantModels`, `EnvironmentGrant`, `_environment_bindings.py` | Preserve strict `extra="forbid"` config shapes and model-ID validation. Runtime node secrets require an explicit pack/node/variable source; a matching environment name grants no authority. Do not add concurrency fields to an unchecked dictionary or copy the host environment into workers. No new operator config is needed merely to consume authored RAES policy. |
| Provider/MCP launch: `workbench/profiles.py`, `agent.py`, `codex_agent.py`, `_raes_participant_transport.py` | Preserve private configuration file checks, exact `{command,args,env}` server shapes, allowed environment keys, credential aliases, config digest checks and exact tool inventory where that adapter requires them. Existing decision-only and tool-enabled adapters have different permissions; do not merge their profiles. Concurrent participants need distinct mutable sessions/workspaces even when they select the same role. |
| Secrets and OS exposure: existing credential sources, `BoundedProcessRunner`, `DeploymentBackend`, `utils/curl_safe.py` | Use approved credential sourcing, minimal per-consumer environments, stdin prompts, private files, admitted executables and bounded I/O/process cleanup. No tokens/prompts in argv, URLs, exception strings or shared temporary filenames. Keep native actions behind `DeploymentBackend` and existing target ownership/network/mount/resource gates. Process supervision is not an OS sandbox; do not grant host homes, daemon sockets or evaluator stores to obtain concurrency. |
| Errors and observability: RAES `Diagnostic`, operation receipts/status, `ParticipantProviderFailure`, `AgentExecutionError`/`BoundedProcessError`, `get_logger()` | Preserve typed, bounded failure translation, including cancellation that is not an ordinary `Exception`. Reuse Python `utils/redaction.py`, MCP `redaction.ts` and `traceToolCall()` at serialization boundaries. Correlate run/attempt, participant/episode, action/operation and execution generation; never dump worker exceptions, provider output or credentials. No new exception hierarchy or concurrency log store. |
| Persistence: `RunStorageBackend`, `LocalRunStore`, participant control/action evidence publishers, evidence coordinator and ADR-050 sealing | Keep run-relative ID/path validation, no-follow containment, create-once transactions, per-run finalization locks, visibility separation and immutable seals. Drain workers and complete evidence before sealing. Do not hold a run finalization lock while waiting for workers that must acquire it. JSONL arrival order is not RAES commit order. |
| Existing external ingress: `api/deps.py`, workbench authorization and MCP common configuration/SSH boundaries | This design needs no new HTTP/WS/MCP endpoint. If exposed through an existing operator surface, retain token, origin, subject, profile and command gates; pass no backend handles or control credentials to participants. Preserve host-key verification and command tracing at the existing MCP boundary. |

## Local concurrency hazards and extension seam

`AptlParticipantRuntime` has a single mutable `_selection_provider`, and
`run_participant_turn()` rebinds it. Its replay/budget maps and in-flight set
use multi-step operations, while pending selections are keyed by solicitation
ID. Parallel calls cannot rely on dictionary atomicity or role labels for
isolation. Bind provider state to run/participant/episode identity at the
existing provider seam; reserve/check/consume atomically and reject duplicate
IDs. Never hold one global lock across native actions and call that concurrency.

`admit_action()` replaces `_behavior_history` with an entire worker snapshot
and publishes `_pending_realization_evidence` immediately after base admission.
With a batch, a worker result precedes the scheduler's final merge. A last-writer
cache can lose a peer's history, and a worker publication can describe an action
the final commit rejects. The authoritative combined history must come from
the settled RAES snapshot. Retain immutable native observations and existing
evidence transactions, but tie claims of accepted state to final settlement;
do not replay side effects to repair publication. The same review applies to
mutable deployment-client/session caches and fixed native artifact paths.

The extension seam belongs in `RuntimeTargetOptions`, admitted plan authority,
and participant implementation/provider bindings: a collection keyed by compiled
participant identity, with supported execution bindings and finite capacities.
Use RAES policy for scheduling/failure behavior, existing adapters for provider
choice, and backend qualification for physical capacity. A third participant,
two participants of the same role, or another provider should not require new
role branches, a second scheduler, or edits to the canonical contract schema.
The manifest must describe the qualified implementation, not promote arbitrary
authored requests into supported capabilities.

## Qualification and repository boundaries

Evidence must exercise real overlap through RAES admission, not just mocks
returning two successes. Use barriers/events and deterministic fakes at native
or provider boundaries to prove overlap and reversed completion order without
sleep-based timing assertions. Cover peer snapshot/credential/view isolation,
same-role distinct identities, duplicate/stale binding rejection, capacity
exhaustion, known failure and timeout, participant/trial cancellation, late
completion after reset, indeterminate batches, evidence failure and sealing
after drain. Verify no failed pre-dispatch admission launches native work and
no dispatched action is silently retried. Keep an adopted-scenario qualification
that proves actual red/blue execution and native cancellation limits.

Reuse `tests/test_bounded_participant_runtime.py`,
`test_raes_participant_delivery.py`, `test_raes_backend.py`,
`test_lilrae_runtime_handoff.py`, `test_workbench_process.py`,
`test_participant_workbench_adapter.py`, `test_workbench_authorization.py`,
`test_execution_executor.py`, and the runstore/evidence/archival suites as
relevant consumers. Manifest tests must include unsupported combinations and
RAES conformance, not only flag assertions.

Whole-repository owners in scope are the backend/RAES adapters, workbench and
MCP boundaries, deployment/environment binding, config models, evidence and
experiment/archival controllers, and provider/guest processes. Canonical
controls are `.ground-control.yaml`, `.gc/plan-rules.md`,
`.gc/pack-ownership.json`, `tools/check_pack_boundary.py`, dependency pins,
`tools/run-targeted-tests.sh`, `.pre-commit-config.yaml`, and
`.github/workflows/checks.yml`. Preserve installed-pack boundaries and existing
identifiers under ADR-062; new artifacts use LilRAE naming. Run targeted tests
and staged-file `pre-commit run` locally; CI owns full suites, conformance gates
and installed-lab qualification. Compose/container/config changes additionally
require their focused contracts and clean installed-lab qualification.

Non-goals: a new participant schema, inter-agent bus, delegation protocol,
shared-context store, portable scheduler, exception family, provider service,
experiment state machine, sandbox framework, public API, or distributed/tenant
orchestration. Joint actions and shared state remain RAES contracts and are not
implied by overlapping red/blue execution. This preflight changes no runtime,
manifest, dependency, scenario, historical requirement status, or test behavior.
