# TechVault static validation gate

`aptl.validation.techvault_gate.validate_scenario()` returns a `GateReport` for the selected SDL file.
It parses, verifies imports, compiles, does conformance checks, and interprets the scenario. It does not start Docker.
The gate uses TechVault as its reference input for issue #322.
The gate accepts other scenarios through the same inputs.

## What the gate checks

| Stage | Pass condition | Important failure case |
| --- | --- | --- |
| Parse | `raes.parse_sdl_file` accepts the selected SDL. | Parse failure ends the report before later stages. |
| Import lock | Declared imports match the adjacent `raes.lock.json`. | Changed imports fail verification when `check_imports` is enabled. |
| Compile | The installed RAES compiler accepts scenario semantics. | Semantic errors fail the check. |
| Backend conformance | The native manifest and target satisfy the selected RAES profile through API and CLI checks. | Missing corpus, profile, or conformance command fails the gate. |
| Provisioning realization | The interpreter produces valid nodes, services, networks, and dependency closure. | Missing, ambiguous, or disabled support services fail realization. |
| Account parity | Declared accounts agree with the provisioner. | Group, mail, SPN, or disabled-state differences fail parity. |

`GateOptions` defaults to `full-remote-control-plane`, with import checking enabled.
Optional corpus roots override the installed wheel's roots.
A scenario without imports needs no import lock.
Selected Compose profiles must agree with public startup's admitted realization.

Scenario names do not select a preset.

## Backend manifest

`create_aptl_manifest()` publishes the native RAES `backend-manifest-v2` declaration.
The profile is a conformance input, separate from Compose profile selection.
A local approximation cannot replace the native manifest.

| Component | LilRAE contract |
| --- | --- |
| `provisioner` | Typed node, network, content, and account realization through the deployment backend. The backend refuses unsupported concerns. |
| `orchestrator` | Workflow execution with decision, parallel, failure, condition, and inject handling. |
| `evaluator` | Conditions, objectives, and result/history envelopes. The retired SDL scoring chain is unsupported. |
| `participant_runtime` | The manifest's declared participant lifecycle, action, observation, and shared-state contracts. |
| `observation` | `null` for the empty default collector registry. An admitted registry can declare its supported observation projection. |
| `cleanup` | `null` for ordinary interactive startup. An installed [cleanup service](declared-cleanup.md) can declare its bounded capabilities. |

Exact capability and contract declarations come from `src/aptl/backends/raes_manifest.py` and its component owners.
Participant observations are participant-runtime data, separate from a standalone observation component.
The compatible processors, concept-authority bindings, and supported contract versions are separate compatibility declarations.
RAES owns the schema and conformance rules.
See the [authoring boundary](../sdl/index.md) for upstream owners.
A static pass does not establish runtime installation, readiness, evidence capture, or broad role support.

## Advisory today, blocking at cutover

The job was advisory during the original cutover.
A failed selected gate now blocks CI.
The `raes-scenario-gate` job in `.github/workflows/checks.yml` has no `continue-on-error` allowance.
Issue #1193 records the cutover.

## Running the gate

See [validate a scenario](scenario-validation.md).
