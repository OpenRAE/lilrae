# Compose a participant trial

Use this How-to guide for trusted application assembly, with approved artifacts and installed participant implementations.
Run behavior verification only in CI or an approved isolated VM.
The [concurrency explanation](../architecture/concurrent-participant-execution.md) defines ownership and qualification limits.

## Bind the admitted configuration

Create a fresh target and installed bindings for each trial.
Use `opencode_manifest` to declare the implementation's configuration targets.
Use RAES configuration realization with `OpenCodeConfigurationValidator` and an admitted model domain.

Resolve prompt artifacts through the caller's approved artifact boundary.
`configured_opencode_executor` checks the prompt reference, exact UTF-8 digest, model, and timeout.
Bind the resulting configuration digest in the participant implementation selection.

Pass the bindings through `ScenarioAdmissionSource.autonomous_bindings` to `admit_raes_scenario`.
`OpenCodeOptions` holds the admitted launch settings; `OpenCodeToolProfile` holds the verified MCP inputs.
For experiments, call `run_participant_workload` from the existing workload callback with the admitted target, plan, and task evaluator.

The caller retains the existing capture and evidence configuration.
