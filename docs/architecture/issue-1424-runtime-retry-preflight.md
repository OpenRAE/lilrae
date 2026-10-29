# Issue #1424: runtime retry ownership preflight

> **Superseded (issue #1407).** RAES 9.0.0 keeps one runtime for the whole run (OpenRAE/rae#1660). After a failed apply, its backend effects are unknown, and RAES refuses another apply. A failed apply now ends the start, and the automatic retry and its `before_backend_retry` hook are removed.

The contract is a clean retry or a clean failure against the same runtime
target. This note sets boundaries for the fix; it is not an implementation
plan or a claim that replay is already safe.

## Findings and ownership decision

`src/aptl/backends/raes.py` admits once, retains a `RuntimeTarget` and an
`ExecutionPlan`, and calls `_run_execution_plan` again for its one automatic
retry. `_apply_execution_plan` constructs an `AptlRuntimeManager` each time.
Admission also constructs a manager for planning. These are distinct managers
over the same component instances. The reported ownership exception is not
defined in this repository; the dependency is pinned to `raes==7.0.0` in
`pyproject.toml`. The exact upstream binding point and supported replay behavior
must be verified with that real manager, not inferred from the exception text.

An execution must have one supported runtime ownership lifecycle across its
applies. Prefer retaining the owning manager rather than constructing another
manager over owned components. Account for the planning manager too if planning
or construction binds ownership. Do not clear private owner attributes, clone
components to evade ownership, monkeypatch the dependency, or bypass
`RuntimeManager.apply`. A second apply is allowed only if the released manager
accepts the admitted plan against its current snapshot and the backend can
safely reconcile the first attempt's effects. Otherwise return a terminal,
actionable failure through the existing outcome path. Catching an exception
alone does not establish retry safety.

Keep these concepts distinct:

- Runtime manager ownership governs in-memory components, snapshots, time,
  participant context and operation state.
- Workspace/project/daemon/native-resource ownership authorizes Docker actions.
  It is enforced by deployment receipts and fresh inspection, not a manager.
- `AcesRunTarget.run_id` identifies the existing lab-start attempt and archive.
  An internal automatic retry retains it; a separately admitted start differs.
  Neither a new manager nor a retry counter establishes new cleanup authority.

`AdmittedScenarioStart` and `AcesStartOutcome` in `raes_start_model.py` are the
existing handoff contracts. If manager lifetime must cross a handoff, use a
typed reference on the existing contract, not a manager registry, singleton,
serialized manager, or second execution/session DTO. The returned manager and
`final_snapshot` must describe the same final execution: lab participant
delivery later consumes `outcome.runtime_manager`.

## Cross-cutting layers that both applies must satisfy

| Layer and canonical incumbent | Guardrail for this fix |
| --- | --- |
| Ingress: `api/main.py`, `api/deps.py::verify_token`, `api/middleware/bff.py`; CLI `cli/lab.py` | Continue through core lab orchestration. Preserve API bearer/session, Host and CSRF gates; add no retry endpoint, token forwarding or client-side retry loop. |
| Configuration: `core/config.py::AptlConfig`, `DeploymentConfig`, `EnvironmentGrant`; `.ground-control.yaml` | Preserve strict config shapes and grant validation. This ownership fix needs no new config, environment variable, dependency or retry-policy schema. |
| Admission: `admit_raes_scenario`, RAES parser/compiler/planner, `AdmittedScenarioStart`, `RuntimeTargetOptions` | Reuse the admitted bundle, target, exact plan, parameters, adapter selections, capture authority and pinned artifact facts. Do not reparse, replan, reacquire a pack or resolve mutable image tags to escape ownership. |
| Runtime call contracts: `raes_planning_compat.py::AptlRuntimeManager`, released RAES input/snapshot contracts, `AptlProvisioner.validate` | Retain existing finite compatibility limits and their restoration. Preserve snapshot transitions, operation contracts, realization provenance and the SEM-218 gate. Never replace them with local validators or fabricate an empty/base snapshot to make replay pass. |
| Deployment policy: `_raes_provisioner_start.py`, `core/execution_boundary.py`, `_compose_runtime_materialization.py`, `runtime_materialization.py` | Revalidate the bound daemon and enforce effective runtime/host authority, mounts, capabilities, namespaces and published-port posture through the existing path on replay. Reusing a manager does not authorize a changed daemon or relaxed realization. |
| Environment and OS delivery: `_environment_bindings.py`, `_compose_environment.py`, `_realization_primitives.py`, `utils/pathsafe.py` | Preserve pack/consumer grants, generated-artifact bindings, variable-name and env-file value checks, sanitized Compose process environment and owner-only no-follow files. Never put credentials in argv, retry logs, exception details, labels or a new snapshot carrier. A retry does not grant ambient environment access. |
| Resource mutation: `_compose_owned_start.py`, `_compose_resource_ownership.py`, `_compose_resource_resolution.py`, `_docker_endpoint_binding.py` | Preserve workspace/project/attempt receipts, bound daemon identity and native-ID checks. Partial Compose failure already captures resources and attempts rollback without removing volumes. Verify the resulting state; a failed or unknown cleanup is not permission to retry destructively. |
| Lifecycle and recovery: `core/lifecycle_guard.py`, `lifecycle_cleanup.py`, `lab.py` recovery persistence | Keep both applies and their preparation inside the existing lifecycle mutation lock. Retain cleanup obligations and evidence of residual state. An API timeout does not stop its worker thread or release its ownership; never launch a replacement execution on that assumption. |
| Failure envelopes: `raes_diagnostics.py`, `_raes_apply_helpers.py`, `_raes_start_failure.py`, `core/lab_types.py`, API `LabActionResponse` | Reuse redacted diagnostics, `LabResult` and `AcesStartOutcome`; no new exception hierarchy or parallel error serializer. Recognize only the actual supported ownership/replay failure at the narrow boundary; do not swallow arbitrary bugs or cancellation with a broad catch. Preserve available failure snapshot/context rather than erasing partial effects. |
| Secrets and observability: `raes_provisioner.py::closed_credential_result`, `_raes_apply_reporting.py`, `utils/redaction.py`, `utils/logging.py` | Credential-bearing applies must still close free-form details. Preserve bounded diagnostic rendering and `_with_backend_failure_diagnostics`; record retry/final failure using existing logging with safe identifiers only. `get_logger` does not itself redact messages. Never dump target, plan, config, environment or backend result objects. |
| Persistence: `AcesRunTarget`, `core/runstore.py`, existing workflow result/history writers and lab provenance | Both applies use the same run store/run ID. Preserve first-failure diagnostics and recovery obligations without inventing another archive format or rewriting sealed evidence. Do not duplicate successful workflows, evaluation histories, participant delivery or time advancement. |

Paths in the table are under `src/aptl/` unless otherwise qualified; deployment
helpers are under `src/aptl/core/deployment/`, backend helpers under
`src/aptl/backends/`. These boundaries implement the relevant parts of
[ADR-046](../adrs/adr-046-dynamic-raes-scenario-realization.md) and the
[resource ownership preflight](issue-964-backend-resource-ownership-preflight.md).
[ADR-055](../adrs/adr-055-local-runtime-authority-and-ownership.md) remains
proposed; this fix must not claim its broader hardening is complete.

## Retry semantics, extensibility and evidence

The retry owner remains `_apply_with_backend_retry`. Its existing
`before_backend_retry` callback is the preparation seam; `lab.py` selects it
from the admitted `ScenarioStartupPlan` and `StartupHook.BEFORE_BACKEND_RETRY`.
Preserve at most two applies and one preparation call, only for the existing
`aptl.provisioner.backend-start-failed` diagnostic. Do not retry deterministic
admission, validation, ownership/policy, workflow or evaluation failures. The
bounded native readback polling in `_raes_provisioner_start.py` is a different
mechanism and must not become another whole-plan retry loop.

The next pack's preparation belongs behind that same identity-bound startup
hook, not a profile-name branch or new retry framework. Manager lifetime is
execution-scoped and passed explicitly; it must work for targets with optional
participant/time runtimes as well as ordinary provisioner/orchestrator/evaluator
components. No global cache keyed by target name or project path.

Replay must address stale-plan/base-snapshot checks and component memory, not
only the ownership exception. Reusing a manager may retain a failed snapshot;
reconstructing one may lose operation history. Verify the released contract
before allowing replay. Success-only workflow driving must remain success-only.
A second failure must return failure, even if its diagnostic remains retryable
as a classification; that flag must not trigger a third apply. Preparation
failure must also reach an honest terminal outcome without hiding existing
residual resources or the original backend failure.

`tests/test_raes_backend.py` already checks single admission, two applies and
callback ordering, but `_FakeRuntimeManager` has no ownership enforcement.
`tests/test_raes_planning_compat.py` also contains a two-manager test with the
upstream constructor replaced. Neither proves production ownership safety.
Required behavioral evidence uses the real pinned manager and real target
components with a controlled deployment backend: first failure then success,
two failures, no eligible retry, unsafe replay/ownership conflict, and failed
preparation. Cover the admission-to-apply handoff, final manager/snapshot
identity, absence of duplicate downstream work, preserved run identity, and
secret canaries in returned errors and captured logs. Owned partial-resource
and cleanup-refusal behavior should reuse `test_compose_resource_ownership.py`
and lifecycle fixtures rather than a separate fake ownership protocol.

Local verification follows `.gc/plan-rules.md`: explicit affected pytest paths
through `bash tools/run-targeted-tests.sh`, then staged-file `pre-commit run`.
CI owns full suites. A live trial, if used as delivery evidence, must use an
approved existing lab and report residual-state/cleanup outcome, not merely
the absence of a Python traceback.

## Non-goals

No implementation here. No RAES fork or version upgrade, general retry/backoff
framework, automatic reset/volume deletion, cross-process runtime resumption,
new durable ownership schema, auth change, pack-specific core behavior, or
unrelated hardening. The delivery PR must satisfy the issue as one change;
requirement-free work does not need a fabricated requirement UID.
