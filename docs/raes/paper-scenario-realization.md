# Paper Scenario Realization

`scenarios/paper-agent-loop.sdl.yaml` is a checkout-only research fixture based on the RAES paper scenario from issue #598.
The ordinary acquired-pack catalog excludes it.
The backend interprets its RAES plan into typed node, network, participant, and evaluator intent.
`DeploymentBackend` owns the native effects.

The `paper-agent-behavior` specification carries `aptl-participant-runtime-binding/v1` on the governed `x-aptl:participant-runtime-binding` extension.
LilRAE parses that binding into the participant command, success markers, target evidence references, and snapshot surfaces.
The binding remains backend-private topology data.
It is not participant-visible placed content.

| Authored node | Backend service | Networks |
| --- | --- | --- |
| `red-workbench` | `aptl-kali` | `redteam-net`, `dmz-net` |
| `customer-portal` | `aptl-webapp` | `dmz-net`, `internal-net` |
| `customer-db` | `aptl-db` | `internal-net` |
| `wazuh-manager` | Wazuh manager | `security-net`, `internal-net` |
| `wazuh-indexer` | Wazuh indexer | `security-net` |

The workbench has no `internal-net` or `security-net` attachment.
The compiled `participant.action-contract.probe-customer-portal-login` action resolves its service references through the runtime plan and backend mapping.
It examines the portal login endpoint from the workbench.
Negative database and Wazuh reachability markers remain evaluator evidence.
They do not enter participant `observable_refs` or `disclosed_refs`.

Use [trace a participant action](../sdl/paper-walkthrough.md) for a learning exercise.
Use the [fixture procedure](../sdl/techvault-curated-variants.md) for the development selection boundary.
The explicit startup command is `lilrae lab start --scenario-path scenarios/paper-agent-loop.sdl.yaml`.
Run it only in an approved isolated lab VM or CI.

## Evidence surfaces

| Surface | Contract |
| --- | --- |
| Participant terminal observation | `paper-agent-view` owns this observation. It travels through `participant-observation-envelope-v1`. It is neither placed content nor an evidence requirement. |
| Wazuh corroboration | `wazuh-evidence` declares capture intent, separate from participant-visible context. |
| Negative reachability checks | `boundary-check-evidence` declares evaluator-only capture intent. |
| Task brief | This content resides at `/home/kali/operations/scenario/task.md` on the existing `kali_operations` volume. |

Evidence requirements keep source, scope, trigger, boundary, channel, sensitivity, redaction, integrity, retention, and loss declarations.
A declaration does not prove collection.
Wazuh evidence does not establish detection quality by itself.

The upstream paper model keeps historical `metrics`, `evaluations`, `tlos`, and `goals` content.
The backend does not realize that retired scoring chain after RAES ADR-073.
It keeps condition/objective evaluation and reports unsupported evaluator sections.

Snapshot entries use the selected participant, action, and observation-boundary addresses.
They must not substitute legacy TechVault SSH identities.

## Upstream Provenance

The fixture keeps the participant behavior, action, and observation surfaces from the upstream #598 scenario.
LilRAE adds local condition bindings.
It omits the optional policy-gate provenance surface because this repository has no real `participant-policy-gate` backend service.

The original related work is RAES #598, second-backend proof #600, and LilRAE participant-provenance issue #554.
[ADR-046](../adrs/adr-046-dynamic-raes-scenario-realization.md) records the evidence-modeling decision.
