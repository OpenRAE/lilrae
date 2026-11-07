# Declared cleanup

LilRAE gives native cleanup for the released RAES trial-service interface.
The shared runtime owns trial progression and cancellation.
Issue #459 gives the full LilRAE trial adapter.
Interactive lab start does not become a terminal trial.

## Install the service

See [Install declared cleanup](install-cleanup.md#install-the-service).

## Evidence and failure

Cleanup records the primary trial outcome separately from cleanup status.
A completed cleanup call can return a valid failed cleanup receipt.
The runtime keeps that receipt and prevents later dispatch.
Successful fresh-range cleanup can claim verified absence within its exact boundary.

It does not claim universal rollback or declared reusable state.

Evidence lives under the configured run's `cleanup/` directory:

- `intents/` keeps the immutable admitted plan and attempt join before effects.
- `content/` keeps bounded, content-addressed native readback.
- `records/` contains the corresponding RAES evidence records.
- `receipts/` contains immutable `TrialCleanupReceiptModel` documents.

These records carry resource states, stable reason codes, and a project-qualified
recovery command. They exclude inspect payloads and raw backend errors.
Publication failure prevents a successful return.
Sealed archives refuse cleanup before native effects begin.
An interruption keeps an unverified receipt when publication remains possible,
then propagates to the runtime owner.

Process death leaves the existing runtime ledger and native receipts for recovery.

Repeated cleanup revalidates native state.
Destroy retires the receipt of each removed container, network, and volume after it records the absence.
A recorded child receipt stays.
Retired receipts permit absence checks, not deletion of replacement volumes.

Foreign, replaced, unreadable, or stale resources do not gain deletion authority.
Container removal does not implicitly remove anonymous volumes or host files.
Named volumes require their own receipt within the bound range.

The emitted receipt passes `validate_trial_cleanup_receipt`.
Its exact receipt reference and distinct attempt identity can be joined by
`validate_batch_execution_receipt` and `validate_trial_unit_result`.
Consumers must also resolve the retained evidence bytes.

## Supported service contract

The default interactive manifest keeps `cleanup` null.
The capability supports idempotent `destroy` and `verify` actions.
The supported probe is `native-absence:<boundary-id>`.

The initial implementation supports a single complete attempt range.
It refuses reset, restore, compensation, custom actions, and declared reuse.
It also refuses multi-attempt retry policies without an installed preparation owner.

The service keeps the released runtime order: capture, native destroy,
then declared cleanup and verification.
An unbound provisioning `DELETE` plan fails before the lab-start realization path.
The trial adapter must give its explicit native deletion owner.
Never replace that refusal with a project-wide stop for a smaller scope.
