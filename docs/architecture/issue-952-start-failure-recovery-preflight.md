# Issue #952: failed-start recovery preflight

The supplied issue is the delivery contract; no Ground Control requirement is
attached. This checkout already has `--teardown-on-failure`, `StartResidue`,
recovery rendering, and focused tests. Extend those incumbents rather than
creating a second recovery workflow. This note fixes boundaries and acceptance
risks, not an implementation sequence. No new ADR is needed: retain
[ADR-029](../adrs/adr-029-control-plane-secret-handling.md),
[ADR-030](../adrs/adr-030-startup-partial-readiness-classification.md),
[ADR-031](../adrs/adr-031-lab-orchestration-contract-guards.md), and the
[issue #905 lifecycle contract](issue-905-lab-lifecycle-robustness-preflight.md).
The [issue #964 ownership contract](issue-964-backend-resource-ownership-preflight.md)
defines the current receipt-backed authority boundary.

## Decisions and invariants

- Default failure preserves the range for diagnosis. Report observed project
  container and network counts, plus `aptl lab stop` and `aptl lab stop -v`
  with their data consequences. Count created and exited containers as well
  as running ones. Volume-only state does not block a subsequent normal start.
- The invocation-scoped `teardown_on_failure=False` parameter belongs in core
  orchestration and is forwarded by CLI and clean boot. It applies to a fatal
  start result, not successful degraded outcomes. Never remove a range rejected
  by `_step_reject_preexisting_range`, even with the flag. An empty checked
  baseline identifies this attempt's possible residue; it is not deletion
  authority over anything later discovered by label.
- Acquire `lifecycle_mutation_lock` before project mutation and retain that
  same ownership through failure observation, optional non-volume stop, and
  checked post-stop observation. Use the already-owned stop seam and original
  backend. Do not release/reacquire, dispatch a separate `aptl lab stop`
  process, or create a new lock. Clean boot keeps its outer reentrant owner.
- Startup outcome, runtime presence, deletion authority, cleanup attempt, and
  cleanup verification are separate facts. An observation error means unknown,
  never zero. `torn_down` requires checked absence of both resource kinds;
  a stop return code alone is insufficient. Keep the original failed result,
  diagnostics, execution boundary, and nonzero exit even if cleanup succeeds.
  Report secondary cleanup failures without replacing the initiating failure.
- Recovery commands must target the start's canonical project root, including
  after `start -d DIR` from another directory. Share the canonical recovery
  wording and data consequences with the pre-existing-range refusal. Retaining
  volumes retains volume-backed data; removing containers loses their writable
  layers and container-local logs. Do not promise that every kind of lab data
  survives. `stop -v` remains an explicit destructive action with its existing
  confirmation gate. Failed `start --clean` cannot restore volumes already
  removed by the requested initial clean boot.

## Cross-cutting passage and canonical reuse

| Layer in scope | Incumbent and required passage |
| --- | --- |
| Core workflow and contracts | `core.lab` owns `_LAB_START_STEPS`, `_LabStartContext`, `_account_for_failed_start`, `_observed_start_residue`, `_tear_down_failed_start`, `_stop_lab_owned`, and `_tear_down_owned`. Retain RAES admission, SEM-218, readiness, terminal evidence, and transcript finalization. Recovery does not reinterpret a backend error string or rerun scenario admission. |
| Config and identity validators | `core.config.AptlConfig` and `DeploymentConfig` are strict `extra="forbid"` shapes; `validate_compose_project_name` bounds project tokens. Existing stop configuration/admitted-profile recovery owns identity resolution. Invalid present config, malformed ownership, or an uncertain target must not fall back to a guessed project. The invocation flag requires no persistent config field, env variable, SDL field, or duplicate validator. |
| Workspace persistence and deletion authority | `_compose_resource_ownership.WorkspaceOwnership` and `ResourceReceipt`, plus `_compose_resource_resolution._prepare_owned_cleanup` and native-ID resolution, bind workspace, effective project, daemon, and attempt. Load the recorded workspace scope before counting. Labels narrow discovery; strict receipts and fresh object/namespace checks authorize removal. Preserve ownership receipts, cleanup records, run archives, `.env`, keys, certificates, and generated host state. |
| OS lock and paths | `core.lifecycle_guard` uses the canonical project root and `.aptl/lifecycle/.lock`; `utils.pathsafe` supplies contained, no-follow descriptor operations. Preserve POSIX owner-only permissions, Windows reparse-point rejection/ACL behavior, same-thread reentrancy, and cross-thread/process exclusion. Lock-file existence and PID metadata confer no ownership. |
| Backend and process exposure | `DeploymentBackend` / `HostInventoryBackend`, `DockerComposeBackend`, `SSHComposeBackend`, `_docker_endpoint_binding`, `_build_command`, `_command_kwargs`, and `_subprocess_kwargs` own runtime access. Reuse list-form argv, explicit project scope, existing timeouts, pinned local endpoint or configured SSH transport, and daemon revalidation. Keep credentials out of argv; never switch to ambient Docker context or a reconstructed local backend for cleanup. |
| Env binding and secret validation | `core.env` owns parsing, `EnvVars`, and placeholder checks. `_environment_bindings` owns pack/consumer/source grants; `_realization_primitives.environment_file_line` checks delivery shape; `_compose_environment.compose_process_environment` limits Compose inheritance. Cleanup introduces no secret source and must retain these gates rather than reloading arbitrary env, inheriting all ambient values, or rebuilding credential-bearing command strings. Existing authenticated probes remain behind `curl_safe`. |
| Runtime observation and teardown | `ProjectRuntimePresence`, `_compose_runtime_inventory`, and `_compose_project_inventory` preserve error channels and all-state, deduplicated inventory. `_compose_stop`, `_compose_project_cleanup`, and receipt-backed resource/network removal own bounded, best-effort teardown and verification. Direct containers and stranded helpers precede network removal. Do not use unchecked prefix/network listing as proof of absence. |
| Results, errors, and observability | `core.lab_types.LabResult`, `StartupOutcome`, `StartupDiagnostic`, `StartResidue`, `STOP_RECOVERY_ROUTES`, and `describe_project_runtime` remain canonical. `_emit_diagnostic`, `utils.logging.get_logger`, and `utils.redaction.redact` own diagnostics/log boundaries. Use counts, stage names, and bounded reasons; no raw Docker stderr, env, receipt payload, or exception/context repr. In particular, raw `icontract.ViolationError` text can contain secrets even after pattern redaction: emit only the safe step/classification. No new exception hierarchy, DTO, inventory store, or telemetry schema. |
| CLI and JSON projections | `cli._start_residue.stop_recovery_routes` / `emit_start_residue`, `cli.lab_render.render_start_result`, and `cli.lab._start_result_fields` project the same result. `_common.emit_json_result` preserves one versioned JSON object, progress on stderr, and exit semantics. Target paths in operator recovery guidance must be safely quoted for the supported shell; never execute the displayed command or print unrelated backend paths. Counts retained after verified teardown describe what was removed; consumers must read `torn_down`, not mistake them for remaining resources. |
| API/auth and web consumers | `api.main` installs `verify_token` and BFF Host/Origin/CSRF/two-factor session gates. `api.deps.get_project_dir`, `api.schemas.LabActionResponse`, the lab router, and `web/src/lib/{api.ts,types.ts,stores/lab.ts}` remain consumers of core behavior. This CLI issue adds no route, request schema, web control, or auth bypass. The current API does not project residue or expose the flag; do not claim parity it does not provide. An `asyncio.wait_for` timeout does not terminate the worker or authorize teardown. |
| Volume reset and host actions | `_compose_volume_cleanup`, receipt-backed `_remove_owned_volumes`, `core.lifecycle_cleanup`, and `startup_reset_state` own explicit volume reset and pending host cleanup. Failure cleanup with `remove_volumes=False` must not run volume-reset actions or mark their records completed. Retain transcript/evidence finalization from ordinary stop. |
| Repository delivery rules | `.ground-control.yaml`, `.gc/plan-rules.md`, `docs/CODING_STANDARDS.md`, `tools/run-targeted-tests.sh`, `.pre-commit-config.yaml`, and `.github/workflows/checks.yml` govern focused pytest, staged hygiene, and CI qualification. `pyproject.toml` remains dependency/entry-point authority. No Compose, Dockerfile, config, dependency, or hosting change is required. Preserve existing `aptl` interfaces under ADR-062; introduce no naming alias. |

## Acceptance risks identified before implementation

- **Anonymous volumes:** `core.ephemeral_containers.remove_container_command`
  always includes `docker rm -v`. `_compose_resource_resolution` uses it for
  receipt-owned lab node removal as well as helper disposal. Consequently,
  passing `remove_volumes=False` does not prove that all node volumes survive.
  Preserve node data volumes, including anonymous ones, on failure cleanup.
  Keep disposable helper storage distinct from node data and retain the helper
  disposal contract. If removal needs a preservation parameter, place it on
  the canonical removal/cleanup seam, with callers selecting the intended
  behavior; do not duplicate argv assembly or weaken every helper globally.
- **Recovery target mismatch:** `_step_reject_preexisting_range` embeds bare
  `STOP_RECOVERY_ROUTES`, whereas the residue renderer qualifies a different
  project root. The refusal must offer equally accurate target selection.
- **Earlier backend compensation:** `_compose_owned_start` already rolls back
  partial Compose failures, independent of the CLI flag. Ownership-capture
  failure calls `_roll_back_started_project` with `remove_volumes=True` by
  default; its existing tests explicitly require `--volumes`. This can remove
  data before core failure accounting runs. Reconcile this existing #1105
  safety contract with #952's retention promise at the existing rollback
  parameter, preserving safe treatment of unreceipted objects. Do not silently
  disable ownership-failure compensation or claim that a later non-volume stop
  preserves data already deleted. Disclose mandatory backend compensation
  separately from optional operator-requested teardown. This path also logs
  and returns raw Compose stderr today; it must pass the bounded error and
  redaction boundary before being exposed as recovery diagnostics.
- **Failure coverage:** the coordinator accounts for returned step failures
  and `icontract` violations. Other escaping exceptions, exceptions in residue
  observation/cleanup, and readiness-publication failures can bypass that
  accounting. Normalize recoverable operational failures at the existing
  core boundary while still owning the attempt; preserve the primary error
  and describe unknown residue when observation fails. Do not catch
  `BaseException` indiscriminately or stringify secret-bearing exceptions.
- **Late supervision:** public start currently invokes `after_start` callbacks
  after releasing its mutation owner. The appliance access supervisor must
  remain outside that owner because it uses shared observation locking.
  Separate finite startup-failure accounting from long-lived supervision;
  never bolt cleanup onto the unlocked callback return and assume no new owner
  intervened. Do not promise failure cleanup for process death or cancellation
  without a separate contract.
- **Partial teardown:** zero runtime residue does not prove transcript or host
  work succeeded, and an unknown inventory does not establish safe deletion
  authority. Keep cleanup diagnostics alongside the independent resource
  verification. Refuse uncertain/foreign ownership, leaving explicit recovery
  guidance instead of broadening the cleanup selector to meet a zero count.
  Runtime-spawned children need their existing backend ownership contract;
  image/name matching or a parent's daemon socket grants no child cleanup
  authority. Project-label counts are not a complete host rollback inventory.

## Extensibility, evidence, and boundaries

The extension seam is the existing invocation parameter on core start/clean
boot, paired with backend-owned observation and stop. A future caller can opt
in without inventing its own recovery coordinator; any future API projection
must map the existing result through its response model and web types. Keep
volume-retention policy at the canonical cleanup boundary, separate from
whether cleanup is requested. No policy framework or generic rollback engine
is needed for this boolean option.

Existing coverage lives in `tests/test_lab.py`, `tests/test_cli.py`,
`tests/test_lifecycle_guard.py`, `tests/test_compose_resource_ownership.py`,
`tests/test_ephemeral_containers.py`, `tests/test_compose_environment_bindings.py`,
and `tests/test_api_lab.py`.
Acceptance evidence must prove both default preservation and opt-in cleanup,
original failure retention, observation/cleanup failure, network-only residue,
pre-existing/foreign workspace protection, correct recovery targets, named and
anonymous data-volume retention, and lock exclusion through post-stop
verification. A fake backend storing `volumes=4` and observing only the stop
boolean cannot establish actual Docker volume behavior. Extend focused unit
coverage; isolated-daemon lifecycle qualification belongs to CI/CD.

Non-goals: fixing Shuffle/SEM-218, changing readiness/degradation semantics,
implicit pre-existing-range reconciliation, automatic retry, daemon-wide prune,
deleting images or host state, new persistence/rollback schemas, background
jobs, cancellation recovery, or expanding API/web functionality. Avoid cleanup
in an unconditional `finally`, CLI-only Docker logic, parsing error prose for
ownership, shell interpolation, and returning startup success because cleanup
succeeded. This preflight changes guidance only; it does not implement fixes.
