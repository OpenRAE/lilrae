# Issue #1423: Shuffle Startup Recovery

## Decision And Evidence

The Shuffle backend selects `runtime-restart-policy: on_failure` through its
existing backend implementation profile. Docker restarts the same container
when its process exits with an error. An orderly exit does not trigger recovery.

The issue's root-cause comment supersedes the initial readiness-probe proposal.
The pinned backend already waits for OpenSearch before index initialization.
A later index request can time out and panic in `InitOpensearchIndexes`.
A startup health dependency cannot prevent that later failure.
The upstream function handles an existing index, so initialization can run again.
Upstream Compose also uses a restart policy for the backend.

This decision uses ADR-046 and ADR-051's existing selection and observation
contracts. It needs no new ADR, startup probe, runtime schema, or retry framework.
The original title describes readiness; the issue discussion identifies crash
recovery as the required repair.

## Architecture And Authority

The catalog matches Shuffle's application semantics, independent of node names.
`select_backend_node_implementation()` supplies the restart value only when the
value is absent and the exact concern has open realization authority.
An authored restart value takes precedence. Missing authority rejects selection.

The typed runtime carries `operational_policy.restart: on_failure`.
The generic Compose renderer emits `restart: on-failure`.
The runtime observer reads `HostConfig.RestartPolicy.Name` from the selected daemon.
RAES compares that observation with the admitted contract.
The renderer and observer need no product-specific changes.

```text
Control plane                         | Docker daemon boundary
Pack declarations -> RAES plan        |
Profile + open authority -> runtime   |
Runtime -> generated Compose -------->| Container restart policy
RAES disclosure <--- daemon readback <| HostConfig.RestartPolicy.Name
                                      |
                                      | Shuffle -- authenticated index requests --> OpenSearch
                                      | Shuffle <------- index responses ---------- OpenSearch
                                      | Shuffle ---------- retained data --------> shuffle_data
                                      | OpenSearch ------- retained indexes ------> shuffle_opensearch_data
```

Docker restarts Shuffle after a nonzero exit. Shuffle repeats its normal
OpenSearch wait and initialization against the retained data.
Existing authenticated service checks remain the startup success boundary.
A restart policy proves recovery configuration, not application readiness.
Persistent datastore failure can still exhaust the existing startup budget.
Docker's `on-failure` policy does not start containers after a daemon restart.

## Security And Failure Controls

| Asset or boundary | Threat | Control and verification |
| --- | --- | --- |
| Authored runtime authority | A profile overrides a closed or authored policy. | Exercise selection with open authority, absent authority, and an authored policy. |
| Datastore credentials | A new health command exposes credentials through process arguments or logs. | Use Docker's restart policy without a new command or credential path. Existing classified bindings remain authoritative. |
| Retained application and index data | Recovery deletes or replaces persistent state. | Restart the existing container. Keep existing volume contract tests. |
| Runtime evidence | Desired configuration is reported as observed state. | Exercise daemon readback with matching and mismatched policies. |
| Startup result | A restart is reported as service readiness. | Keep existing authenticated readiness and failure handling. |

Internal datastore TLS and frontend certificate verification retain their
separate admitted contracts. Recovery adds no ports, capabilities, mounts,
Docker socket access, image changes, or external data flows.
Local and SSH deployments use the same generated policy and backend observation.
Repeated failures remain visible through existing startup diagnostics and logs.

## Executable Design And Verification

The implementation catalog is the architecture-as-code change.
Existing authority validation and RAES disclosure are the policy-as-code controls.
No new enforcement layer or requirement UID is introduced.
Regression tests cover released-pack realization and generated Compose.
Selection tests cover semantic matching, authored precedence, and absent authority.
Daemon observation tests cover `on-failure` normalization and rejection of mismatch.
Full clean-lab and loaded-host qualification belong to CI/CD.

## References And Document Review

- [Docker restart policies](https://docs.docker.com/engine/containers/start-containers-automatically/): Engine documentation, consulted 2026-10-25; policy behavior and manual-stop semantics.
- [Compose services](https://docs.docker.com/reference/compose-file/services/): Compose Specification, consulted 2026-10-25; `restart` syntax.
- [Shuffle deployment](https://github.com/Shuffle/Shuffle/blob/main/docker-compose.yml): upstream reference architecture, consulted 2026-10-25; backend restart policy.
- [Shuffle shared](https://github.com/Shuffle/shuffle-shared/blob/v1.2.51/db-connector.go): v1.2.51; index initialization and existing-index handling.
- [ASD writing guidance](https://www.asd-ste100.org/about_STE.html): Issue 9 overview; short sentences, consistent technical terms, and one meaning per term.

The document review checks technical names, short sentences, and one fact per
sentence against the published ASD guidance. This note describes system behavior;
implementation tasks and workflow evidence belong on the issue.
