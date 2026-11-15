# Connect trial readiness

Use this How-to guide when composing an admitted native trial.
Behavior verification runs only in CI or an approved isolated VM.
Use an already approved placement, installed owners, and the exact selected runtime target.
This procedure does not approve a VM, resolve new credentials, or acquire another provider.

The source owners are `src/aptl/backends/readiness.py`, `installed_readiness.py`, and `trial_services.py`.
[Trial serving](../architecture/trial-serving.md#required-readiness) explains the shared gate and fences.

## Compose the shared gate

Construct `TrialReadiness` with the public `TrialRealizationInputs` and a
`ReadinessEnvironment` for the exact installed runtime target. The environment
supplies approved native owners, local artifact access, the selected collector
registry, the run store, the clock, and the existing `ProbeProcessRunner`.
The native target must expose its provisioner readiness port.

Its effect
adapters share this same gate. Do not construct another runtime for readiness.
Wrap installed trial services in `ReadinessTrialServices` before RAES admission.

Pass the gate to `LilraeTrialUnit`; a missing gate refuses dispatch.

The wrapper records the ordinary clean-placement check while it holds both
placement locks. Preparation reconstructs the sealed selected entry, checks
its processor plans and snapshot, and verifies installed configuration,
artifact, backend, capture, containment, and storage obligations.
A fully ceased preparation refusal releases only fences newly claimed by that invocation.
Existing ownership and uncertain probes retain their fences. A retry rechecks clean placement.

`InstalledReadiness` connects the ordinary Docker backend, approved placement
record, participant executor ports, installed collectors, and local run store.
Use `executor.readiness_owner(manifest)` for each configured participant.
Supply the same collectors used for capture and their source clocks.

Each source must expose a separate bounded, read-only readiness operation.
Acquisition, stimuli, and remote write probes stay in the capture lifecycle.
Sources without that read-only operation refuse readiness.

`create_gate(inputs, target, scenario_root, registry)` attaches the resulting gate.
Pass it to both `ReadinessTrialServices` and `LilraeTrialUnit`.
The placement record must come from the already approved lab owner.

Supply `AppliancePlacementReadiness` with that owner's policy, binding, and
fresh host and guest observation methods. The ordinary boundary qualifier
must confirm identity, perimeter, and enforcement. Missing or invalid proof
fails even when the endpoint and daemon match.

This check does not approve a new VM.

Collector registrations pin any `clock_accuracy_ms` requirement in their
configuration digest. The gate reads the admitted value; a missing clock fails
when accuracy is required. Native startup's selected `minimum_max_map_count`
passes unchanged to the ordinary system requirement owner.

Missing or unknown
ownership fails that required check.
Artifacts are checked locally without pulls or materialization.
Provider readiness uses the selected implementation build and approved access
operation; a model label or configuration digest alone cannot pass.

The OpenCode executor exposes `readiness_owner(manifest)` for its actual
configuration, bounded build probe, and configured provider readiness operation.

After complete provisioning, the gate checks required services and capture
sources before effects. Orchestration, evaluation, and participant adapters
also enforce the gate. The Docker service check reuses ordinary container,
listener, and authenticated service checks against the selected durable graph.
Missing sources, collector wiring, writable output, or required capability
refuse execution. Source clocks need measured accuracy only when their selected
capture contract requires it. A baseline on an approved existing VM requires
no cloud account or final factorial matrix.

Readiness retains immutable observations under `readiness/clean/`,
`readiness/prepared/`, and `readiness/live/`. Digests bind every observation to
its plan, entry, run, attempt, snapshot, target, and selected configurations.
Fixed diagnostics identify failed checks without source output or exceptions.
Run storage and each separate capture destination must prove write capacity;
captures sharing a destination share one aggregate capacity check.
The handoff names readiness observations for the existing archive inventory.
Storage failure blocks execution, including an otherwise passing verdict.

A failed readiness check does not erase successful native provisioning.
RAES commits those effects so its cleanup can remove them.
`ReadinessTrialServices` refuses a successful workload claim after a readiness
failure while preserving native cessation and evidence verification.

Partial capture, stop, and cleanup remain available after readiness fails.
A timed-out probe does not establish cessation. Outstanding probe calls or
unverified process cleanup retain the placement fences and block handoff.

See [the readiness design](../architecture/exp-011-resource-readiness-design.md).
