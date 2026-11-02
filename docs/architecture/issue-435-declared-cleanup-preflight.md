# Issue #435: Declared cleanup preflight

The issue payload is the delivery contract. This note fixes boundaries for
DSL-007; it is not an implementation plan. No new ADR is needed: ADR-029,
ADR-046, ADR-050's released-producer successor clause, ADR-055, and ADR-064
already assign the relevant owners.

## Decisions

- **RAES owns portable cleanup semantics.** Use released
  `TrialCleanupPlanModel`, `TrialCleanupReceiptModel`,
  `CleanupObligationResultModel`, and `validate_trial_cleanup_receipt` from
  `raes_contracts.contracts`. The inspected repository lock and installed wheel
  both select RAES 10.2.0. Its corpus includes truthful required-cleanup failure
  receipts; do not reproduce the former rule that required cleanup must succeed
  for a receipt to be valid. Native GitHub dependency relationships still govern
  delivery readiness; this inspection does not certify their closure.
- **One runtime owns execution and cleanup.** Build on the released
  `BackendTrialUnit` / `TrialUnitRequest` / `TrialUnitResult` handoff and
  `TrialRuntimeServices` cleanup, stop, verification, and retry-preparation
  seam. RAES owns supervision, operation admission, idempotency, cancellation,
  reconciliation, and trial-phase progression. LilRAE supplies native effects
  and evidence. Do not drive a second lifecycle from the CLI, admission
  controller, collector, or a new scheduler. `ExperimentController.admit`
  remains effect-free. Preserve the single runtime owner used by
  `AptlRuntimeManager`; never instantiate a replacement manager to replay an
  uncertain failed apply.
- **Declared scope is not native authority.** Resolve portable boundary and
  resource references through backend-owned bindings to recorded native
  resources. `owner_ref`, authored labels, names, image matches, and a shared
  project string cannot authorize deletion. Require the same daemon,
  workspace, effective project, admitted attempt, receipt, and fresh native
  owner checks as other backend operations. Trial cleanup selects its exact
  boundaries/attempt; explicit project recovery may cover multiple recorded
  attempts. Neither may absorb unrelated resources to unblock removal.
- **Cleanup, reset, rollback, and evidence retention are separate promises.**
  Destroying containers does not implement a declared reset, restore,
  compensation, or clean-state probe. A required action needs an admitted
  implementation and verification capability before execution begins. Unknown
  kinds, profiles, references, or unsupported required probes fail admission;
  if support is lost after effects, retain an honest unsupported/unverified
  result. Do not interpret profile/probe references as shell, Python, import
  paths, arbitrary host paths, or backend method names.
- **Record facts before irreversible effects and before sealing.** Establish
  execution cessation, retain execution/evaluation observations and partial
  capture, perform owed teardown and cleanup, then retain verified cleanup
  evidence for terminal archival. Respect released runtime ordering rather
  than duplicate it. A failed capture must remain visible and cannot silently
  suppress required cleanup. Container writable layers and local logs disappear
  on removal; retaining volumes alone does not retain them.

## Required cross-cutting passage

| Layer | Canonical incumbent and required guardrail |
| --- | --- |
| Portable input and result validation | RAES sealed-plan ingress, `TrialUnitRequest` reconstruction, processor plans, cleanup model validators, `validate_trial_cleanup_receipt`, and `validate_trial_unit_result`. Preserve bounded values, dependency order, trigger coverage, plan/entry/run/attempt joins, target/run operation scope, and evidence coverage. These validators own portable semantics; add only native capability/authority checks, not copied schemas or invariant registries. |
| Capability admission | `raes_manifest.create_aptl_manifest`, admitted family trial/provenance, `AptlProvisioner.validate`, and the released trial-service admission seam. Resolve supported actions and evidence owners without side effects. Do not advertise generic cleanup support because `backend.stop()` exists or insert an extra manifest claim to bypass refusal. |
| Runtime and lifecycle control | RAES runtime operation ledger and trial services; `core.lab`'s `_stop_lab_owned`, `stop_lab`, `clean_boot_lab`, failed-start accounting, and `lifecycle_guard.lifecycle_mutation_lock`. Retain one canonical root and mutation owner; use the already-owned seam under a held lock, not recursive public stop or a separate command. Follow ADR-064: entry code composes adapters; application code receives core protocols, without new application/adapter import cycles or mixins. |
| Native ownership and runtime children | `WorkspaceOwnership`, `ResourceReceipt`, `_compose_resource_resolution`, `_compose_owner_labels`, `_compose_project_cleanup`, and Docker recording lifecycle helpers. Labels narrow discovery; receipts and fresh checks authorize native-ID operations. Quiesce producers, reconcile in-flight creation, and remove recorded children/helpers before dependent networks/volumes. Keep recording completion and unknown creation state visible. A pending producer is not an empty inventory. |
| Backend, daemon, and OS/process boundary | `DeploymentBackend`, local/SSH Compose implementations, `_docker_endpoint_binding`, `_run`/`_run_with_input`, and existing subprocess environment/timeout helpers. Retain the original configured transport and bound daemon, list-form argv, bounded output, and endpoint revalidation. No raw Docker/subprocess call in the controller; no ambient context fallback, secret-bearing argv, or new remote transfer. Remote files require a provider-owned operation, not local `Path.unlink`. |
| Configuration and environment shapes | Strict `AptlConfig`/`DeploymentConfig`, `validate_compose_project_name`, `core.env.EnvVars` and placeholder checks, `_environment_bindings` consumer/source grants, `_realization_primitives.environment_file_line`, and `_compose_environment.compose_process_environment`. Cleanup needs no new env source or config dialect. Any existing authenticated probe keeps its approved binding and `curl_safe` sink; a cleanup reference cannot select arbitrary env values or bypass delivery validation. |
| Host filesystem and durable action state | `utils.pathsafe` contained descriptor-relative no-follow operations and `core.startup_reset_state` / `core.lifecycle_cleanup`. Fixed owner-approved host actions retain their action version, pack identity/provenance, completion markers, and absent-target behavior. They run at their existing volume-reset boundary; ordinary trial cleanup cannot blindly run every pending pack reset or delete `.aptl`, source packs, `.env`, credentials, or archives. Unsafe/unreadable paths differ from absent targets. |
| Native evidence and persistence | `deployment.lilrae_native_evidence.confirm_native_absence` / `record_cleanup`, `LilraeRuntimeEvidence`, `LilraeMaterializationArchive`, evidence coordinator/records, injected `RunStorageBackend`/`LocalRunStore`, and archival coordinator/seal. Native witnesses prove bounded effects and grant no deletion authority. Publish safe evidence create-once through the configured store, bind digests/references, retain failed attempts, and finish writes before the atomic seal. Recovery after a seal uses separate immutable evidence/attestation with lineage, never edits sealed bytes. |
| Errors, logs, telemetry, and public surfaces | RAES category errors and `Diagnostic`/`ApplyResult`; `LabResult`, `StartupDiagnostic`, `StartResidue`, and `render_raes_diagnostics(stage_label=...)`; `get_logger`/`redact` and ADR-029. Preserve the primary failure and add bounded secondary cleanup failures. Emit obligation/resource reference, stage, safe reason and recovery route; omit raw exceptions, validation inputs, stderr, env, payloads, credentials, and host paths from public envelopes and OTel attributes. Do not add an exception hierarchy or cleanup response DTO. |
| Authentication and consumers | Existing CLI confirmation/JSON rendering and recovery routes; API `verify_token`, BFF Host/Origin/CSRF/session gates, `get_project_dir`, and `LabActionResponse`. Core behavior must be shared. This issue needs no new endpoint, authentication bypass, web control, or changed authority based on a client-supplied path. An API/worker timeout does not prove the worker or its effects stopped. |
| Repository and host qualification | `.ground-control.yaml`, `.gc/plan-rules.md`, `docs/CODING_STANDARDS.md`, `pyproject.toml`, `uv.lock`, hashed `requirements/` exports, `.pre-commit-config.yaml`, `tools/run-targeted-tests.sh`, and `.github/workflows/checks.yml`. Use locked released APIs, targeted local tests and staged hygiene. CI owns full suites, installed-wheel/backend qualification, and fresh-lab checks when lifecycle/config/runtime changes require them. Do not add a service or dependency to obtain cleanup. |

## Failure, interruption, and contract gotchas

- The released request keeps `run_id` from the admitted entry and a distinct
  `execution_attempt_id`. The existing `core.execution.executor` uses an older
  model with the attempt as the archive run ID. Likewise, older prose in
  ADR-047/050 and the #964 preflight predates the released distinction. At this
  boundary, retain explicit plan/entry/run/attempt/native-attempt bindings and
  use released producers/validators. Do not rename a portable run to the
  attempt, equate both IDs, overwrite historical archives, or guess lineage
  from names. Resolving this join is a prerequisite to batch-consumable evidence.
- RAES 10.2.0's trial runtime captures before native destroy and calls the
  cleanup service afterward. Verify that `AptlProvisioner.apply` actually
  implements the runtime's delete-plan semantics: its current path is oriented
  toward realization/start. Do not route delete through start. Reset/restore
  operations needing live resources must be compatible with the released
  ordering or be refused before execution; do not silently substitute destroy
  or patch RAES internals. `AptlOrchestrator.stop` and `AptlEvaluator.stop` clear
  in-memory results/history; preserve observations before either call.
- `_tear_down_failed_start` can set `StartResidue.torn_down` from checked
  container/network absence even when stop reported another failure. That is a
  narrow runtime-presence fact, not proof of all declared cleanup. Likewise,
  `_remove_owned_attempt_containers` is best-effort compensation, not a verified
  successful receipt. Aggregate `LabResult.success` and zero counts cannot
  supply per-obligation evidence or authorize a clean-state claim.
- Existing stop may span every receipt in a workspace. Reuse its native
  primitives with an explicit admitted selection; never expand a trial's scope
  to the whole project merely because it is easier. Compose aggregate teardown
  requires its existing exclusive namespace verification. Legacy prefix volume
  discovery in `_compose_volume_cleanup` is not authority for new cleanup:
  use receipt-backed volume removal. Volumes have reusable names, so retain
  fresh owner checks, absence witnesses, and verified receipt retirement.
- Repeated cleanup is at least once across process death, not exactly once.
  Effects can finish before their completion record is durable. Reconcile
  native state and operation records before retry; do not replay an unknown
  operation. Respect declared idempotency, dependency order, compensation,
  per-obligation timeout, and retry policy. Continue independent safe work after
  a failure without running a dependent action whose prerequisite failed.
  Required owed actions cannot be omitted or reported `skipped` to satisfy the
  receipt validator; report their actual supported/failed/unverified outcome.
- Cancellation/timeout requires observed cessation, including runtime-spawned
  children and in-flight producers. SIGKILL/power loss cannot run `finally`;
  durable ownership/action/operation state must support later reconciliation.
  Keep unknown residue and resource reservations until proven safe. Do not
  release a range for the next trial merely because cancellation was requested.
- Preserve trial outcome independently of cleanup outcome. Required-cleanup
  failure permits a valid failure receipt, not a successful clean-state claim.
  `validate_trial_cleanup_receipt` checks structural joins; authorized evidence
  owners must resolve bytes and execute admitted probes. For batch use, retain
  `cleanup_receipt_ref` and pass `validate_batch_execution_receipt` with the
  exact sealed plan and cleanup receipt. References alone do not prove effects.
- Recovery must identify safe residual references and use the canonical
  project-qualified, shell-quoted recovery route. Distinguish non-volume stop
  from an explicitly destructive reset/`stop -v`; neither promises arbitrary
  restoration. Persist original diagnostics and partial evidence even when
  verification or receipt publication fails. Do not print or execute arbitrary
  commands supplied by the scenario or raw backend errors.

## Extension seam and evidence bar

Parameterize the existing native cleanup boundary by admitted resource
selection, action kind/version/profile, verification owner, preservation policy,
and bounded deadline. The binding is trusted composition, not user-selected
code. A second backend or supported reset then supplies the same typed result
and owner-native evidence without changing portable models or lifecycle logic.
Use the existing versioned host-action compatibility seam for host effects;
do not create another cleanup registry or durable ledger.

Focused verification must exercise the actual released cleanup/trial/batch
validators and corpus failure fixtures alongside the existing ownership,
Docker-recording, lifecycle, executor, evidence, archival, pathsafe, and redaction
tests. Cover success/failure/cancellation/timeout, repeated and interrupted
cleanup, effect-before-marker crash, changed daemon, foreign same-name objects,
corrupt/missing authority, children created during cancellation, dependency or
probe failure, retained volumes/files, missing evidence, and failed receipt
publication. Assert unrelated resources are untouched and that a required
failed/unverified obligation never yields rollback-complete or range-reusable.

## Non-goals

No new cleanup DSL/schema, portable record builder, scheduler, workflow engine,
exception family, plugin loader, broad pruning, arbitrary host deletion,
universal rollback promise, or reconstruction of lost evidence. Do not redesign
admission, authentication, storage, ownership, or explicit lab-reset policy.
This slice implements declared native cleanup and its evidence integration; it
does not implement batch scheduling, statistical analysis, or historical archive
migration. Preserve interactive lab-start behavior: successful start is not a
terminal trial and must not immediately tear down the running lab.
