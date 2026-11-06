# Install declared cleanup

Use this How-to guide in trusted trial-service composition.
Use CI or an approved isolated lab VM for tests and native operations.
Before you grant resource authority, read the [cleanup reference](declared-cleanup.md).

## Install the service

1. Get the admitted native attempt and its exact resource ownership receipts.
2. Construct `CleanupBinding` with its entry, run, execution attempt, native attempt, range, owner, and admitted resource references.
3. Construct `ReceiptCleanup` with the configured Docker backend and that binding.
4. Ask the archive owner to create the run before cleanup begins.
5. Construct `DeclaredCleanup` with the admitted `TrialCleanupPlanModel`, native cleanup owner, `LocalRunStore`, and observation clock.
6. Delegate trial-service admission to `DeclaredCleanup.admit`.
7. Delegate cleanup to `DeclaredCleanup.cleanup`.
8. Delegate observation verification to `DeclaredCleanup.verify_observation`.
9. After you install this service, declare `CLEANUP_CAPABILITIES` through `create_aptl_manifest(cleanup=...)`.
10. Keep the existing configuration, execution, capture, stop, and retry owners.
11. Before you permit later dispatch, examine retained cleanup receipts and evidence.

Do not construct authority from an authored owner string alone.
Do not replace a refused scoped deletion with a project-wide stop.
The [supported service contract](declared-cleanup.md#supported-service-contract) states unsupported actions and retry limits.
