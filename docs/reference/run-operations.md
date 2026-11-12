# Prepare and inspect run evidence

Use an approved isolated lab VM for lifecycle operations.
The [run reference](experiment-runs.md) defines storage, provenance, seals, status, and recovery limits.

## Clean State Between Runs

1. Examine the selected project and Docker daemon before destructive cleanup.
2. Keep required earlier evidence in the approved run store.
3. Examine the [cleanup contract](experiment-runs.md#clean-state-between-runs).
4. Request cleanup followed by ordinary startup:

```shell
lilrae lab start --clean
```

5. Before you authorize volume removal, read the confirmation.
6. Use `--yes` only when automation explicitly authorizes destruction of the selected lab data.
7. Examine the startup outcome and new run identity.
8. Before you attempt another run, diagnose cleanup failures.

Do not describe a failed cleanup as a clean starting state.
Use `lilrae lab validate-live --skip-clean-boot` only when inspection of the existing range is intended.

## Compose trial services

1. Get the already admitted `TrialUnitRequest` from the existing RAES owner.
2. Pass its runtime unit, `DeclaredCleanup`, and selected Docker backend to `LilraeTrialUnit`.
3. Use the same placement-state root for every worker on that daemon.
4. Compose `ReadinessEnvironment` from the approved lab owners.
5. Wrap installed trial services in `ReadinessTrialServices`.
6. Bind `TrialReadiness` to the same runtime target.
7. Configure required artifact, participant, placement, containment, capture, and storage checks.
8. Keep the admitted entry, run, and attempt identities during delivery.

Do not replace the admitted plan or schedule another batch through this adapter.

## Recover an assigned trial

1. Keep the original attempt identity, placement records, and RAES ledger after interruption.
2. Reopen the original durable RAES stores after restart.
3. Reconstruct the original `LilraeTrialUnit` and `AssignedTrial` through their existing owners.
4. Pass the coordinator cancellation control, worker runtime, observation clock, and execution identity.
5. Call `aptl.backends.trial_recovery.recover_interrupted_trial` with those original inputs.
6. Examine execution, capture, and cleanup states separately.
7. Before you claim completion, resolve retained partial-evidence and cessation limitations.
8. Examine declared cleanup, native absence, and probe cessation before any placement reuse.

Do not delete ownership records to permit a new trial.
Do not allocate a replacement identity during recovery.
If the result requires another range, use a new approved placement.
An immutable archive alone does not authorize reuse.

## Inspect and export

1. Use `lilrae runs list` to identify available working-run manifests.
2. Use `lilrae runs show <run-id>` to examine the selected run.
3. Use `lilrae runs path <run-id>` for its configured storage location.
4. Examine the returned archive path separately for an assigned trial's sealed snapshot.
5. Use [bundle export](evidence-bundle-operations.md) for portable integrity verification.

Do not infer a seal from a working manifest or a successful export.

## Recover a failed start

1. Examine the startup outcome, diagnostics, and reported retained-resource counts.
2. Select the exact project from the failed operation.
3. Use `lilrae lab stop` to stop its resources and keep volumes.
4. Use `lilrae lab stop -v` only when managed-volume destruction is intended.
5. When you operate outside that project directory, include `--project-dir`.
6. Examine retained anonymous volumes separately before reuse or explicit removal.
7. Resolve uncertain ownership before another startup or cleanup.

For automatic failed-start teardown, select `--teardown-on-failure` before startup.
The [CLI reference](cli.md#destructive-and-emergency-operations) defines preserved data and ownership limits.
