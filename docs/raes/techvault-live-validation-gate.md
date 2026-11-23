# TechVault live validation gate

`aptl.validation.techvault_live_gate.validate_live_deployment()` validates the admitted deployment through the public startup path.
It returns a `VerificationReport` with scenario, backend, run, attempt, and check identities.
The gate uses TechVault as its reference input for issue #323.

The default gate removes project volumes before startup.
The [live validation procedure](live-validation.md) requires CI or an approved isolated lab VM.
A profile mismatch stops validation before destructive boot.

## What the gate checks

| Stage | Contract |
| --- | --- |
| Run identity | Reject an invalid requested run ID before native work. |
| Static prerequisite | Parse, compile, and conformance must pass before boot. |
| Boot-input agreement | The requested profile must match the public startup profile. |
| RAES-driven boot | Interpret admitted content, compute dependency closure, and start through `orchestrate_lab_start()`. |
| Readiness | Compare admitted nodes and apparatus with running resources. |
| Semantic verification | Invoke the exact qualified scenario verifier through bounded operations. |
| Orchestration containment | Recheck runtime authority after semantic work. Include dynamically created children. |
| Scenario variation | Distinct declared node content must produce distinct realization details. |
| Archive | Persist the completed checks, provenance, snapshot, and evidence summary. |

A failed boot skips later checks that require a usable range.
The gate still attempts to archive the available evidence.
The gate resolves the acquired bundle before validation.
Startup keeps the original pack selector so associated artifacts use the correct resolver.

## Failure categories

The closed categories are `raes_specification`, `backend_interpretation`, `backend_instantiation`,
`defensive_stack_readiness`, `kali_reachability`, and `evidence_capture`.
Diagnostics identify the failed layer without raw backend errors or secret-bearing payloads.
A blocked verification has no semantic verdict.
It is not a pass or a detection failure.

## Run-archive manifest

The gate writes `<run-store>/<run-id>/live-gate/manifest.json` with schema `aptl.live-gate.manifest/v1`.
The manifest contains these sections:

| Section | Meaning |
| --- | --- |
| `scenario` | This section records the admitted scenario path and identity. |
| `raes_provenance` | This section records resource-addressed realization details, selected profiles, and interpretation diagnostics. |
| `validation` | This section records identities, categories, outcomes, and diagnostics. |
| `snapshot` | This section records post-boot containers, networks, health, and endpoints. |
| `evidence` | This section records a bounded telemetry summary without raw payloads. |
| `evaluator_surfaces` | This section indexes declared condition/objective result and history contracts. This index is not a score. |

The run store applies redaction before persistence.
An archive describes the observed execution. It cannot replace authored SDL or prove unobserved behavior.

## Observable surface

The acquired bundle gives the startup contract.
The interpreter derives its node, network, service, and apparatus surface.
A reduced research fixture has a separate [curated proof](techvault-curated-live-validation-gate.md).
Historical full-range results do not qualify a current reduced fixture.

## Prerequisites

See [live validation prerequisites](live-validation.md#prerequisites).

## Where the semantic verdict comes from

The `aptl.scenario_verifiers` entry point selects one compatible installed adapter.
The bundled TechVault adapter examines attacker reachability to its shared-network peers.
Its verifier does not generate the former Nmap and failed-SSH attack probes.

Startup still performs required native evidence checks.
Those checks can generate SQL-injection, MISP, and log-producer activity.
The result is not a zero-event baseline.
See the [adapter reference](https://github.com/OpenRAE/lilrae/blob/dev/src/aptl_techvault/README.md).

A live-gate pass alone does not prove that a new attack traversed every detection path.

Qualification binds the exact pack identity, version, digest, extension API, backend target, profile, and transport.
Missing, empty, incompatible, or ambiguous adapter declarations produce `blocked`.
Package version ranges do not establish qualification.

## Running the gate

See [validate a running scenario](live-validation.md).
