# Compose a family adapter

Use trusted entry assembly and an approved installed adapter distribution.
The [family adapter reference](family-adapters.md) owns imports, entry-point names, qualification fields, and refusal conditions.
Run behavior checks only in CI or an approved isolated VM.

## Register the adapter

1. Implement providers for the six required entry-point groups.
2. Register provider instances or no-argument classes under the exact entry names in the reference.
3. Declare literal callable and family API versions in each provider.
4. Declare a host dependency range that includes the first required API release.
5. Declare exact `qualified_family_targets` with pack, family, and backend identities.
6. Pass stable provider identities and `supported_pack_id`.
7. Install all required providers and auxiliary entries from the same qualified distribution and version.
8. Examine qualification before backend preparation.

Do not combine registrations from unrelated providers.
Do not use a pack field as an executable import locator.

## Compile and admit a trial

1. Stage the selected pack with `env_pack_bundle` from `aptl.core.scenario_bundle`.
2. Load its experiments with `raes_env_packs.load_pack_experiments`.
3. Before you seal the trial plan, resolve adapter-owned runtime parameters.
4. Use `resolve_family_runtime_parameters(bundle, target)` when the adapter gives those parameters.
5. Include their binding provenance in RAES admission.
6. Join the experiment with trusted apparatus through `PackExperiment.compilation_request`.
7. Compile the request with `raes_processor.trial_compiler.compile_admitted_trial_plan`.
8. Select the sealed entry and its validated `PackExperiment.family`.
9. Construct `FamilyTrialInput(plan, plan_entry_id, family)`.
10. If you supply a snapshot, use its exact canonical bytes in `snapshot=snapshot_bytes`.
11. Wrap the trial in `ScenarioAdmissionRun` from `aptl.backends.raes_start_model`.
12. Pass that run to `aptl.backends.raes.admit_raes_scenario`.

For family trials, omit a preselected startup provider.
Core selects and pins the exact qualified providers.
If you use a preselected bundle, give `ScenarioAdmissionSource` through its supported source argument.
Do not add new parameter values after the plan is sealed.

## Start and finalize

1. Use protected `LocalRunStore` storage for family snapshots.
2. Use the trial's preallocated run ID for `AcesRunTarget`, if you pass an explicit target.
3. Start through `start_raes_scenario` with the admitted scenario start.
4. Keep snapshot and provenance values out of logs and repository metadata.
5. Before you accept requested facts, make sure that native readback verifies them.
6. Before you admit the next trial, complete the previous trial's declared cleanup.
7. Resume transcript finalization through the original qualified provider installation.

Use the [run recovery procedure](run-operations.md#recover-an-assigned-trial) for an interrupted assigned trial.
The [historical release tuple](family-adapters.md#supported-release-tuple) qualifies only its stated structural checks.
It is not general execution or record-production evidence.
