# ADR-044: RAES-Aligned Run Reproducibility Record

## Status

accepted

## Date

2026-06-25

## Reader boundary

This Explanation records design reasons and constraints.
Dated examples, versions, estimates, and measurements describe their stated revision.
They do not establish current interface support or installed qualification.
The [run Reference](../reference/experiment-runs.md) describes maintained use.
The record's status and amendments still determine its decision scope.

## Context

REP-001 requires every run to preserve enough information to reproduce or audit
the run after the TechVault cutover to RAES. A missing field is not the main risk. A second local manifest would duplicate RAES task, run, apparatus, evidence, and provenance contracts.

APTL already has the pieces this record must compose:

- RAES SDL parsing and semantic validation enter through `raes.parse_sdl_file`
  and the RAES `RuntimeManager`.
- APTL's backend capability claim is published by
  `src/aptl/backends/raes_manifest.py:create_aptl_manifest()`. The current
  code satisfies the `full-remote-control-plane` profile and passes the
  corresponding conformance tests; do not copy older `provisioning-only`,
  `orchestration-capable`, or `orchestration-evaluation` wording from dated
  planning records into new records.
- RAES provisioning, orchestration, and evaluation state is adapted through
  `AptlProvisioner`, `AptlOrchestrator`, `AptlEvaluator`,
  `AptlRealization`, `ApplyResult`, `RuntimeSnapshot`, operation
  receipt/status, workflow result/history, and evaluation result/history
  contracts.
- APTL backend realization evidence is already owned by `DeploymentBackend`,
  `capture_snapshot()`, `RangeSnapshot.to_dict()`, `LocalRunStore`,
  collectors, MCP run capture, and exporter packaging.
- ADR-029 makes `LocalRunStore.write_json`, `write_jsonl`, and
  `append_jsonl` the Python persistence serialization boundary for run
  archives, with `write_file` and `copy_file` explicitly pass-through.

## Decision

The REP-001 reproducibility record is a composition record. It anchors run
identity to RAES contracts where RAES has a contract, and it carries APTL-only
data only as backend realization evidence or evidence references.

When a RAES contract exists for a concept, the record stores that contract
payload or a stable identity reference to it. LilRAE must not mirror RAES task, run, apparatus, evidence, provenance, manifest, receipt/status, runtime snapshot, workflow, or evaluation models.

Backend evidence can include profiles, dependency closure, realization details, snapshot identity, configuration/image/rule digests, tools, parameters, seeds, and source-evidence references. These remain backend observations, not replacement portable models. Those sections
must be clearly backend-owned and must not become the canonical scenario or
runtime schema.

Runtime state has two distinct meanings and must stay separated:

- RAES `RuntimeSnapshot` is the portable RAES state/provenance surface.
- APTL `RangeSnapshot` is backend inventory evidence for the realized lab.

Both may be referenced by one run record, but neither replaces the other.

Structured run-record writes go through `LocalRunStore.write_json`,
`write_jsonl`, or `append_jsonl`. Opaque evidence can stay in existing capture or export storage. Structured records should reference its paths and digests rather than copy bytes into another JSON object.
Exporter code remains packaging-only and must not become the first redaction or
normalization point.

Issue #557 applies the same separation to participant action evidence. Once a
RAES participant transition is accepted, APTL first publishes one immutable
run-scoped transaction through `LocalRunStore.create_run_json_once()`. That
transaction contains the participant and evaluator projections together;
their JSONL streams are derived, recoverable indexes. Failure of either index
does not rewrite or erase the accepted RAES snapshot, but it is an explicit
qualification failure. The create-once path is RFC 8785 canonical,
create-exclusive, descriptor-relative, and no-follow for every component.

When APTL pins a complete RAES `RuntimeModel` as backend authority, it uses a
versioned backend-owned artifact envelope and RFC 8785 canonical JSON. The
digest covers every model field, rejects unsupported values, and never depends
on mapping insertion order or `default=str`. This artifact is reproducibility
evidence for the admitted compiled model; it is not a replacement RAES
runtime-model contract.

## Security Layers

| Layer | Requirement |
| --- | --- |
| RAES parser and validator gate | Scenario inputs continue through `raes.parse_sdl_file`, RAES semantic validation, `RuntimeManager.plan()`, and planner diagnostics. Do not structurally revalidate RAES SDL with local models. |
| Backend manifest and conformance gate | `create_aptl_manifest()` supplies the serialized `backend-manifest-v2` identity. It declares contract versions, processors, realization, concept bindings, provisioner, orchestrator, and evaluator capabilities. |
| Runtime contract gate | Operation receipt/status, RAES `RuntimeSnapshot`, workflow result/history, and evaluation result/history are the portable runtime surfaces. Backend exceptions are translated into redacted RAES diagnostics or `LabResult` errors at the adapter boundary. |
| Deployment inventory gate | Docker, Compose, container, network, image, port, and host inventory flows through `DeploymentBackend` and existing snapshot helpers. Do not parse `docker-compose.yml` or call raw Docker from a record builder. |
| Config and env binding | Durable non-secret settings come from strict `AptlConfig`; runtime secrets come from `.env` / `EnvVars`, placeholder checks, ADR-028 generated config, and ADR-034 SOC TLS material. The record may store digests and non-secret identities, not `.env` values, rendered config secrets, API tokens, cookies, private keys, or bearer material. |
| Persistence and path containment | `LocalRunStore` owns run IDs, relative-path validation, run directory layout, redacted JSON/JSONL writes, and immutable run-scoped transactions through `create_run_json_once()`. Authoritative create-once records use descriptor-relative no-follow containment rather than the legacy resolved-path writer. |
| Snapshot serialization | APTL range inventory enters JSON through `RangeSnapshot.to_dict()`, preserving ADR-029 redaction for service credentials and other secret-shaped fields. |
| Collector and SOC HTTP safety | Collectors stay fault-tolerant, log counts/status only, and use `curl_safe` where SOC API calls need token/body handling that avoids argv leakage. |
| API and error envelope | If the record is later exposed through the web API, it must use the existing `verify_token` / `WebAuthSettings` boundary and existing Pydantic response projection style. Error text must be generic and redacted; auth tokens do not travel in URLs. |
| OS/process exposure | Do not introduce subprocess calls that put tokens, hashes, cookies, passwords, private key material, or rendered secret config in process argv. File modes and ignored directories are defense in depth only. |
| Export boundary | `exporter.py` packages already-safe run artifacts and computes checksums. It must not mutate records to hide leaks that were written earlier. |

## Maintainability

Canonical incumbents for REP-001 are:

- `src/aptl/backends/raes_manifest.py` for backend identity and supported RAES
  contract versions.
- `src/aptl/backends/raes.py`,
  `src/aptl/backends/raes_realization.py`,
  `src/aptl/backends/raes_realization_model.py`,
  `src/aptl/backends/raes_orchestrator.py`,
  `src/aptl/backends/raes_evaluator.py`, and
  `src/aptl/backends/raes_diagnostics.py` for the RAES adapter boundary.
- `src/aptl/core/deployment/` for all Docker/Compose/container/host
  interaction.
- `src/aptl/core/snapshot.py` and `src/aptl/core/endpoints.py` for APTL range
  inventory and endpoint annotation.
- `src/aptl/core/runstore.py`, `src/aptl/core/collectors.py`, and
  `src/aptl/core/exporter.py` for run archive persistence, collection, and
  packaging.
- `src/aptl/core/session.py` and `src/aptl/core/telemetry.py` for
  cross-process trace/run correlation.
- `src/aptl/core/config.py`, `src/aptl/core/env.py`,
  `src/aptl/core/credentials.py`, and `src/aptl/utils/redaction.py` for
  config, env, generated secret handling, and serialization redaction.
- `mcp/aptl-mcp-common/src/runs.ts`,
  `mcp/aptl-mcp-common/src/redaction.ts`, and `mcp/mcp-red/src/capture.ts`
  for TypeScript-side run capture and redaction parity.

Tests should extend the existing seams rather than introduce new harnesses:
`tests/test_raes_backend.py`, `tests/test_snapshot.py`,
`tests/test_runstore.py`, `tests/test_exporter.py`, `tests/test_collectors.py`,
`tests/test_session.py`, and the MCP redaction/run-capture tests.

## Extensibility

The extensibility seam is the boundary between RAES contract identity and APTL
backend evidence references.

Future RAES contract additions for task/run/apparatus/evidence/provenance should
replace APTL-specific placeholders at the RAES namespace, without changing the
backend evidence namespace. Another native evidence source should add a reference and digest/path metadata under the backend namespace. It should not change RAES payloads or add TechVault-only fields.

The record must be parameterized by backend name, backend manifest version,
supported contract versions, compatible processor identity, scenario identity,
and run identity. It must not assume a single scenario, permanent Docker-only deployment, or an unchanging manifest profile name.

## Non-Goals

- Do not design a new APTL scenario schema, experiment manifest schema, or RAES
  mirror schema.
- Do not promote `RangeSnapshot` to the RAES `RuntimeSnapshot` role or flatten
  RAES runtime state into APTL snapshot fields.
- Do not redesign run archive layout, exporter packaging, OTel tracing,
  MCP capture, web auth, deployment backends, or config/env binding as part of
  REP-001.
- Do not make the run archive a plaintext secret vault or full forensic image.
- Do not add a new exception hierarchy, validation framework, redaction helper,
  or logging taxonomy for reproducibility records.
- Do not change APTL's backend profile claim as part of the record unless the
  RAES manifest and conformance tests change in the same backend-focused work.

## Anti-Patterns

- Creating `ExperimentManifest`, `AcesRunManifest`, or similar local types that
  restate RAES contract fields.
- Storing backend-specific evidence at the top level so it looks portable.
- Treating image tags as image identity when a digest is available.
- Treating `.env` hashes or file permissions as permission to expose `.env`
  values, rendered config secrets, tokens, or private keys.
- Calling `docker`, `docker compose`, `curl`, or `ssh` directly from a record
  builder instead of using the existing backend, collector, or safe-curl
  boundary.
- Copying raw evidence into JSON through `write_file` / `copy_file` and assuming
  the runstore redacted it.
- Letting API, CLI, or exporter code become a second normalizer for the same
  record shape.
- Hardcoding TechVault scenario names, compose profile names, or a stale backend
  profile string in the canonical record.

## References

- [ADR-023](adr-023-container-interaction-in-deployment-backend.md): container
  interaction belongs on the deployment backend.
- [ADR-029](adr-029-control-plane-secret-handling.md): runstore and snapshot
  redaction boundaries.
- [ADR-033](adr-033-agent-reasoning-trace-boundary.md): per-run MCP/Kali capture
  layout and trace correlation.
- [ADR-035](adr-035-raes-sdl-adoption.md): RAES adoption and adapter guardrails.
- [ADR-036](adr-036-snapshot-endpoint-registry.md): snapshot endpoint registry
  boundary.
- [ADR-039](adr-039-web-control-plane-authentication.md): web API auth and error
  boundary.
- [ADR-041](adr-041-kali-capture-sidecar-ownership-boundary.md) and
  [ADR-042](adr-042-sidecar-owned-pty-master.md): Kali capture ownership and
  transcript authenticity.
- REP-001 / GitHub issue #423.
