# Serving RAES trials

Issue #459 implements the released `BackendTrialUnit` boundary. RAES owns the
sealed plan, request derivation, runtime admission, operation ledger, deadlines,
cancellation, replacement and resume. LilRAE wraps an already admitted runtime
unit; it never creates an experiment or advances an independent plan.

## Ownership and flow

`RAES scheduler -> LilraeTrialUnit -> RAES BackendTrialUnit -> installed owners`

The adapter receives the selected Docker backend, its declared cleanup owner,
and a trusted shared local placement-state directory. Every worker serving the
same daemon must use that directory. A daemon identity hash selects the lock
namespace; independent daemons have independent namespaces. This is the fixed
single-VM placement boundary, not a distributed allocator.
Trial serving requires the approved POSIX host for descriptor-relative native
state. Ordinary Windows lifecycle commands retain their handle-relative lock
and fence checks; the Windows primitives live in `core._lifecycle_windows`.

Before dispatch, reconstruct the request, enforce the installed operation and
attempt-time limits, and check exact cleanup identity. Acquire the daemon and
project locks, then check project containers, networks, volumes and retained
native receipts for contamination. Persist matching project and daemon fences
before calling the runtime unit. Only the same admitted attempt can reconcile
an existing fence, through the same RAES ledger. No exception or elapsed timeout
proves cessation or authorizes a different attempt.

RAES retains partial observations before teardown and invokes declared cleanup
after success, failure, cancellation or timeout. Validate the returned joins and
verify the cleanup owner's retained evidence and live readback. Remove fences
only after RAES's scope-complete resource-reuse predicate succeeds. Cleanup
failure and fresh-range-required outcomes retain the fences. Evidence remains
in the injected run store. Archival recovery seals an interrupted record; it
does not resume execution. The legacy archival executor has no batch entry point.

The existing lifecycle lock gains context propagation for RAES's AnyIO worker
callbacks. A delegated callback can enter the same live lock, while unrelated
threads and processes cannot. A stale context cannot revive released ownership.
A durable project fence also excludes ordinary lifecycle mutation after a crash.

## Security and executable checks

| Risk | Control | Evidence |
| --- | --- | --- |
| Cross-trial state | Checked project inventory and native absence; cleanup-before-reuse | Contamination and cleanup-failure tests |
| Concurrent work | OS daemon and project locks, durable attempt fences | Independent-project and lifecycle exclusion tests |
| Abandoned work | Fences survive exceptions and process exit | Pending/reconciliation tests |
| Unsafe timeout/cancel | RAES stop, observation and cleanup progression | Released runtime integration tests |
| Resource exhaustion | Bounded portable request and installed operation/time ceiling | Limit tests before dispatch |
| Path substitution | Existing descriptor-relative no-follow helpers | Symlink and fence tests |

Requests and placement inputs come from trusted composition, not a network
endpoint. No new transport, service, credential resolver or upload is added.
`BackendTrialUnit`, `TrialUnitRequest`, `DeclaredCleanup` and the lifecycle lock
are the executable boundaries. ADR-047's released-contract successor applies;
no new experiment state machine or architecture decision is introduced.
