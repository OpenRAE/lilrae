# Issue #437: Interrupted trial recovery

Architecture guidance, not an implementation plan or a claim of shipped recovery.
The supplied #437 contract governs scope. Reuse [trial serving](trial-serving.md),
its cross-cutting gates, and ADR-047/050's released-contract successor clauses.
No new ADR, controller, portable schema or recovery service is needed.

## Released API boundary

RAES 10.7.0 publishes [RAE #1870](https://github.com/OpenRAE/rae/issues/1870)'s assigned-trial API.
The published wheel's SHA-256 is `4000dea8106f5173d55bda6f9c223c0a4d1f984046d72072bd066704c6791a3e`.
Its Python requirement, `>=3.14,<3.15`, matches LilRAE.
LilRAE requires `raes>=10.7.0,<11`; the lock and generated requirements retain exact artifact hashes.
No unreleased dependency or private runtime API is needed.

| Public boundary | Recovery role |
| --- | --- |
| `RuntimeControlPlane.bind_assigned_trial` | Binds the exact admitted entry, attempt, installed services and original durable stores. |
| `AssignedTrial.advance` | Applies delivered coordinator control and reconciles the same attempt. |
| `AssignedTrial.outcome` | Reads retained partial or terminal facts with their original identities and timestamps. |
| `TrialAssignmentControlModel` | Carries coordinator-owned cancellation intent for the exact assignment. |
| `RuntimeControlPlane.ingest_trial_outcome` | Validates original owner observations against the coordinator's admission. |
| `RuntimeControlPlane.experiment_records` | Produces records from retained observations without dispatch. |

Ordinary advancement can still execute workload.
Recovery must receive authorized stop intent rather than manufacture experiment-wide cancellation.
It must prohibit new workload effects while it reconciles owed stop, capture and cleanup.
The runtime retains cancellation in its existing ledger before its stop path runs.
Stop acknowledgement alone does not establish cessation.
Partial outcome export preserves that uncertainty.
Verify these properties through the public boundary in the approved test environment.

## Authority and identity

RAES owns experiment resume, entry selection, cancellation, replacement and the
durable operation ledger. LilRAE reconciles this trial's owned resources and
archives verified retained facts. Recovery must not invoke a workload, advance
a serial plan, replan, allocate another run or select a retry. Reconciliation of
already owed stop/capture/cleanup through the RAES owner differs from resuming
participant execution.

Preserve the RAES-preallocated `run_id`, distinct `execution_attempt_id`, plan
and entry digests, instantiated snapshot, native attempt, project, workspace and
daemon joins. The older executor's attempt-ID-as-run-ID convention does not
apply to the released route. Reject incompatible identities; never sanitize
them into different IDs.

At assessment, `core/execution/executor.py:recover_interrupted_attempt` checked
intent presence without validating contents, substituted recovery time for
original start time, supplied empty acquisition facts, and returned on seal-marker
presence. Its module docstring claimed authority superseded by the released route. Those are
gaps, not recovery precedents. The CLI currently exposes admission only and
trial serving already prohibits local plan resume. Remove remaining local
resume behavior if present without adding a resume interface or deleting shared
archival primitives.

## Recovery invariants

- Intent is a routing/identity commitment, not deletion authority or proof of
  effects. Validate version, exact shape, bounded bytes, duplicate keys, IDs,
  digests and timestamps against retained admission/runtime facts. Preserve
  original event times; recovery has a separate clock-owned observation time.
  Missing, corrupt, conflicting or unsupported data never means clean or never
  started. Only verified pre-effect state establishes no execution. Do not
  fabricate identities or evidence to force corrupt data into a valid record.
- Execution, cessation, capture, cleanup, publication and seal integrity remain
  separate. A successful cleanup `ApplyResult` can contain a failed receipt.
  `TrialPending`, timeout and process loss do not prove cessation. Feed partial
  facts to the released producer, without another status-precedence table or
  successful-evaluation default.
- Retain actual evidence records/bytes, collector reports, loss/truncation
  disclosures, participant history, cleanup readback and provenance before
  teardown discards sources. Lifecycle/cleanup evidence cannot satisfy missing
  task capture. Absent required facts remain explicit limitations or visible
  validation failures, never fabricated empty success.
- Serialize recovery with serving using the same daemon placement and canonical
  project locks, lock order and durable owner fences. Revalidate daemon/owner
  before effects. A dead caller or expired timeout does not authorize takeover
  of a live worker. Preserve delegated lock context; never bypass the fence.
- `CleanupBinding`, `DeclaredCleanup` and `ReceiptCleanup` own reconciliation.
  Revalidate `WorkspaceOwnership`/`ResourceReceipt` native IDs, attempt and daemon.
  Account for pending creation, descendants, recording producers and recreated
  resources. Names/labels only narrow discovery. Unknown/foreign ownership grants
  no destructive action; empty inventory alone proves no absence. No daemon
  prune, broad Compose teardown or authored selector may widen cleanup scope.
- Sealing and placement release are independent commits. Use the released
  record producer with injected evidence reader/archive and the local atomic
  seal/index boundary. Quiesce writers whose artifacts enter the closed
  inventory. If required bytes cannot yet be committed, retain a recoverable
  unsealed candidate. A valid interrupted record may retain uncertain cleanup
  and a fence; a seal alone never grants reuse.
- Release fences only with verified cleanup, complete probe cessation and the
  released `replacement_resources_reusable` predicate. Unknown cleanup and
  publication failure retain both project and daemon fences. Later cleanup
  cannot mutate sealed bytes: use supported version/attestation lineage and
  retained owner state, without a second portable cleanup history.
- Duplicate/concurrent recovery reconciles the same ledger and canonical bytes.
  Reuse retained times and receipts. Accept an existing archive through
  `verify_sealed_archive`, not `is_sealed`. Reconcile prepared/committed entries
  through `DiscoveryIndex`: a seal does not prove index commit or fence release
  finished. Differing prepublished manifests/seals are conflicts, never overwrite
  opportunities.

## Whole-repository gates and incumbents

Paths are relative to `src/aptl` unless stated otherwise. The detailed
[trial-serving gates](trial-serving.md#cross-cutting-gates) also apply.

| Layer | Required reuse and passage |
| --- | --- |
| Contracts/runtime | `TrialUnitRequest`, `validate_trial_unit_result`, released cleanup validators and `RuntimeControlPlane.experiment_records` own joins and portable semantics. `TrialOutcomeReporting`/`report_trial_outcomes` are the reporting seam. Check APIs against `pyproject.toml` and `uv.lock`, not older docs' installed-version observations. No private RAES imports or mirrored DTOs. |
| Parsing/validation | `core/experiment/spec_loading.py`, `AdmissionPolicy`, `ProjectContainedResolver`, `scenario_trial_archive.py` and retained runtime commitments establish bounded pinned inputs. Reuse parsing/containment patterns for intent. `LocalRunStore.read_run_json` alone provides neither strict shape nor duplicate-key validation. Verify and parse the same opened bytes. Local routing journals must not duplicate experiment models. |
| Config/env/secrets | Strict `AptlConfig`, `ExperimentSettings`, `ScenarioSourceConfig`, `EnvVars`, placeholder checks, `_credential_sources.py`, deployment `_environment_bindings.py`/`_compose_environment.py` and explicit `EnvironmentGrant` remain authoritative. Use retained approved configuration, never ambient env to reconstruct authority. No new setting/env field or secret resolver is needed. Installed stop/capture owners resolve their admitted credential sources. |
| Authentication/authorization | Trusted local composition supplies runtime, target, native owner and store. No listener is needed. Existing API paths retain `api/deps.py:verify_token`, `WebAuthSettings`, BFF Host/CSRF/session gates, request limits and narrow responses. Participant evidence access differs from operator cleanup authority. No new hosting, uploads or services. |
| Host/process exposure | Preserve `DeploymentBackend`, `ReceiptCleanup`, `CleanupDeadline`, lifecycle/placement locks, `core/trial_ownership.py`, runtime authority and VM containment. Preserve POSIX serving admission and Windows lifecycle exclusion. Reuse installed bounded process/stop owners and `utils/curl_safe.py`; credentials never enter argv, URLs or displayed commands. Do not launch another participant to recover. |
| Evidence/storage/export | Reuse `core/evidence/{coordinator,records,content_store}.py`, `cleanup_evidence.py`, `LilraeRuntimeEvidence`, provenance/correlation clocks, `LocalRunStore`, `utils/pathsafe.py`, archival seal/verify/index and read-only exporter. One injected store owns private no-follow files, create-once publication and finalization locks. Preserve safe canonical bytes; `SecretInvariantError` prevents redaction changing identity-bearing content. Opaque writes require already-safe bytes. A seal is neither a signature nor a task verdict. |
| Errors/observability | Reuse RAES `Diagnostic`, bounded serving codes, ownership/storage/verification errors and stage-aware `render_raes_diagnostics`. `core/experiment/errors.py` demonstrates safe validation normalization; recovery must not be mislabeled admission. Use `get_logger`, shared `redact`, `RangeSnapshot.to_dict()` and `RedactingSpanExporter`. Emit safe IDs, phases, codes and counts; no raw parser/Pydantic input, exception chains, stderr, secrets or captured content in envelopes/logs/spans. Logging alone does not sanitize. |
| Architecture/workflow | ADR-064 and `pyproject.toml`'s layer map apply: entry composition injects owners; core never imports adapters; adapters do not import application orchestration. Reuse `tools/check_architecture.py`, `tools/check_pack_boundary.py`, `.ground-control.yaml`, `.gc/plan-rules.md`, staged `pre-commit run` and `tools/run-targeted-tests.sh`. Shared MCP/config/lifecycle changes retain consumer and installed-lab qualification lanes. |

## Extension seam and evidence boundary

Parameterize recovery by the admitted request and retained RAES ledger,
installed `CleanupOwner` binding, injected store, clock, evidence reader and
record archive. Another native backend or capture source supplies these ports;
it must not require scenario-name branches, another journal/state machine,
hardcoded roots or an attempt-ID factory. Unsupported released recovery/archive
contracts are dependency gaps, not permission to emulate RAES.

Extend existing trial-serving, cleanup-runtime, receipt-cleanup, executor,
archival-security/seal/index and lifecycle-guard fixtures. Evidence must cover
interruption before effects, after effects but before receipt publication,
during capture/cleanup/seal/index/fence release, duplicate/concurrent recovery,
corrupt intent, foreign/replaced resources, unknown cessation and failed cleanup.
Assert retained partial bytes, identity joins and fence exclusion, not just an
aborted status. Focused mutation checks must detect dropped joins/lost evidence,
unknown-to-success defaults and premature fence release. Tests run only in CI
or an approved isolated VM; full suites stay CI-only. This preflight runs none.

Non-goals: implementation, experiment scheduling/resume/retry policy, another
schema/exception hierarchy/status taxonomy, new API/storage services, archive
migration, sealed-byte repair, broader cleanup authority, credential/deployment
redesign, statistical analysis, or a general legacy-executor refactor.
