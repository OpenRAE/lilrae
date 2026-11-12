# ADR-035: Adopt RAES SDL as APTL's Scenario Authoring Surface

## Status

accepted (amended 2026-06-29, 2026-07-12, and 2026-07-19 by [ADR-046](adr-046-dynamic-raes-scenario-realization.md))

## Date

2026-05-18 (amended 2026-06-29, 2026-07-12, 2026-07-19)

## Last Updated

2026-07-19

## Status update—2026-06-29

The realization model in this ADR (specifically the Parity Inventory Boundary's
statement that topology, profiles, networks, static IPs, hostnames, volumes,
health checks, published ports, and service dependencies come from
`docker-compose.yml` and the `DeploymentBackend` inventory methods) is
**superseded by [ADR-046](adr-046-dynamic-raes-scenario-realization.md)**.
ADR-046 establishes that the compiled RAES `RuntimeModel`, interpreted through
`interpret_provisioning_plan`, is the authoritative topology source;
`docker-compose.yml` remains the realization vehicle selected by profile rather
than the topology authority.

The retained decision uses RAES authoring, backend manifests, conformance, and `DeploymentBackend` execution. The integration guardrails remain in force.

## Status update—2026-07-12

**Superseded further, by [ADR-046](adr-046-dynamic-raes-scenario-realization.md)'s
Capture Inventory and Parity-Inventory Removal Addendum.** The original TechVault inventory statements are historical. `scenarios/techvault.sdl.yaml`, `scenarios/techvault/`, and `scenarios/aces.lock.json` were removed. So were SCN-010 parity files, `check_parity_manifest`, and `required_surface_coverage`.

The body below no longer supplies current parity evidence. The asset-inventory capture capability now lives in
RAES; APTL keeps only `scenarios/techvault-operational.sdl.yaml` as the
driving contract, with no separate capture/parity evidence surface behind it.
This is a point-in-time correction, not a rewrite of the decision record
below—see ADR-046 for the current state.

## Status update—2026-07-19

**Superseded further, by [ADR-046](adr-046-dynamic-raes-scenario-realization.md)'s
TechVault Full Dynamic Cutover Addendum.** The remaining compatibility statement
that `docker-compose.yml` is the profile-selected realization vehicle is no
longer true for the operational TechVault scenario. Compose remains a derived deployment format. The admitted RAES realization graph supplies it. Standalone Compose is not a separate authoring, topology, service-catalog, profile, or lifecycle authority. A checked-in Compose
file, if retained, is a deterministic reference artifact only.

## Reader boundary

This Explanation records design reasons and constraints.
Dated examples, versions, estimates, and measurements describe their stated revision.
They do not establish current interface support or installed qualification.
The [SDL guide](../sdl/index.md) describes maintained use.
The record's status and amendments still determine its decision scope.

## Context

APTL and the Agentic Cyber Environment System (RAES, sibling repository at
`../raes`, `autarchy-ai/aces` upstream) are part of a single research
program. RAES is a backend-agnostic scenario description language with a
published contract surface (`backend-manifest-v2`, `runtime-snapshot-v1`,
`operation-receipt-v1` / `operation-status-v1`, workflow and evaluation
result/history envelopes, provisioning/orchestration/evaluation plan
contracts) and four published backend capability profiles
(`provisioning-only`, `orchestration-capable`, `orchestration-evaluation`,
`full-remote-control-plane`) under `contracts/profiles/backend/`. RAES's
runtime stack is `raes.core.sdl` → `raes.core.runtime` → `raes.backends.*`,
driven by a `RuntimeManager` that compiles SDL into a typed `RuntimeModel`,
plans a composite `ExecutionPlan` (provisioning + orchestration +
evaluation), and applies it against a registered `RuntimeTarget`. A backend
target is integrated by publishing a `backend-manifest-v2` claiming
conformance to a named profile and passing `raes conformance backend
--profile <name>` against that manifest.

RAES owns cross-backend reproducibility. LilRAE supplies a realistic native backend that exercises those contracts in a purple-team lab.

The earlier tree owned `aptl.core.sdl` and the SCN-001 Pydantic YAML schema in `aptl.core.scenarios`. DSL-001 through DSL-009 tracked their grammar, parser, and validation. Both languages began from Open Cyber Range SDL. The local fork overlapped RAES while its names and scope diverged.

Carrying two SDLs has three concrete costs:

1. **Cross-backend reproducibility—the central RAES claim—cannot be
   demonstrated using APTL scenarios** because their grammar is
   APTL-private. The research program cannot show "the same scenario ran
   on backend A and backend B" while APTL refuses to read the same
   document the other backends do.
2. **Every DSL-002..DSL-009 feature is duplicate work** against
   equivalent RAES features (variables/runtime substitution, composition,
   pre/post-conditions, CACAO/Attack Flow alignment, cleanup/rollback,
   topology declaration, user-behavior profiles).
3. **Existing RAES tooling** includes resolution, import verification, publication, `raes.lock.json`, OCI distribution, MCP, and conformance. Matching that support would duplicate upstream work.

Implementation status as of 2026-06-25: public lab startup now defaults to the
RAES-authored operational TechVault SDL through `start_raes_scenario()`,
`scenarios/catalog.json`, and the RAES runtime manager. APTL has since promoted
its backend manifest and gates beyond the Phase A bootstrap claims. Issue #530 covered remaining reconciliation. Local SDL/YAML surfaces and stale documentation or tests needed removal or quarantine so they could not appear authoritative.

## Decision

APTL adopts RAES SDL as its canonical scenario authoring surface and
implements a RAES backend target that wraps APTL's existing lab.

Specifically:

- Authored scenarios are RAES SDL documents parsed by `raes.parse_sdl`
  / `parse_sdl_file` against RAES's published schemas and semantic
  validators.
- APTL implements one `RuntimeTarget` registered into the RAES runtime
  target registry and publishes a `backend-manifest-v2` from
  `src/aptl/backends/raes_manifest.py:create_aptl_manifest()`. The manifest and conformance results determine a backend profile claim. Historical planning names cannot replace them.
- APTL's CLI delegates `aptl lab start` and friends through the RAES
  `RuntimeManager` lifecycle (compile → plan → validate → apply → start
  orchestrator/evaluator → stop) instead of the current imperative Python
  lifecycle.
- APTL's published backend manifest is validated by the RAES target
  conformance runner and the published `raes conformance backend --profile
  <current-profile>` CLI path used by the static/live gates.
- During Phase A, the legacy `aptl.core.sdl` parser and `scenarios/*.yaml`
  Pydantic path remained functional. The `raes`
  dependency, the RAES backend target, and the RAES TechVault scenario
  land as a *parallel* path during Phase A.
- At cutover (Phase B, a single PR), the public startup path flipped to the
  RAES-authored operational TechVault SDL
  (`scenarios/techvault-operational.sdl.yaml`). The deeper
  `scenarios/techvault.sdl.yaml` remains the detailed inventory/parity
  artifact rather than the runtime boot contract. Legacy `scenarios/*.yaml`
  moved to `scenarios/archive/` as strictly reference-only material (not
  loaded by any runtime path), `aptl.core.sdl` is deleted,
  `aptl.core.scenarios` remains only as shared session/continuity exception
  types, and Pydantic `ScenarioDefinition` models are
  deleted.

## Backend Profile Choice

APTL targeted `provisioning-only` initially because that profile requires only
`backend-manifest-v2`, `operation-receipt-v1`, `operation-status-v1`, and
`runtime-snapshot-v1`—all reachable by wrapping the existing lab provisioning
code. Issue #311 added the historical orchestration-capable profile. It declared `capabilities.orchestrator`, `workflow-result-envelope-v1`, and `workflow-history-event-stream-v1`. `aptl.backends.raes_orchestrator` supplied the concrete orchestrator, and scenario startup used RAES control. Issue #312 then promoted the evaluator surface through
`aptl.backends.raes_evaluator` and the evaluation result/history contracts.

Current code may advance beyond those historical milestones. The canonical
profile claim is whatever `create_aptl_manifest()` plus the static/live gates
validate today; as of this update those paths target
`full-remote-control-plane`. Cleanup work must not preserve older
`provisioning-only`, `orchestration-capable`, or `orchestration-evaluation`
wording as a current contract unless it is clearly labeled historical.

## Parity Gate

Before cutover, the RAES TechVault scenario had to reach capability parity
with the union of the legacy scenario set now archived under
`scenarios/archive/`. Concretely it had to exercise:

- the same node / service / vulnerability / feature surfaces
- the same injects and scenario flow shapes
- the same objectives and scoring outputs (where SCN-007 applies)
- the same run-archive surfaces captured for current scenarios

The parity check was reviewed in the cutover PR description as a hard
prerequisite. Post-cutover cleanup continues to preserve the inventory as the
audit surface.

## Parity Inventory Boundary

Issue #318's parity inventory is the authoritative review surface for
deciding whether the RAES TechVault can replace the legacy scenario set. It
is not a runtime schema, not a new SDL, and not a deployment authority.

The inventory lived at `docs/raes/parity-inventory.yaml` with a
human-readable overview at `docs/raes/parity-inventory.md`. Its schema
was enforced by `tests/test_parity_inventory.py`. (Both files and that test
were removed; see the 2026-07-12 status update above.)

The inventory must map every legacy surface to exactly one owning category:

- **RAES SDL** when the authored scenario can express the surface directly
  through the RAES parser, schemas, semantic validators, and compiled
  `RuntimeModel`.
- **RAES schema/profile gap** when RAES owns the concept. Such a row must identify an upstream follow-up rather than restore the retired local SDL.
- **APTL backend responsibility** when the concept is backend realization
  detail: Docker Compose profiles, generated runtime config, lab-managed TLS,
  SOC seed material, deployment inventory, readiness classification, snapshots,
  run archive persistence, or host/container interaction.
- **Validation gate** when the surface is not authored but must be proven by
  conformance, static parity tests, live lab validation, snapshots, or run
  archive assertions.
- **Cutover-only archive/cleanup** when the legacy field is retained only as
  reference material after the Phase B move to `scenarios/archive/`.

The canonical source for a row is the existing owner, not the inventory
document itself. In particular:

- authored legacy fields now come from archived reference fixtures under
  `scenarios/archive/`;
- topology, profiles, networks, static IPs, hostnames, volumes, health checks,
  published ports, and service dependencies come from `docker-compose.yml` and
  the `DeploymentBackend` inventory methods;
- durable first-party knobs come from `AptlConfig`, not ad hoc YAML keys;
- `.env` values and generated secret-bearing config come from `EnvVars`,
  `find_placeholder_env_values`, ADR-028, ADR-029, and ADR-034;
- lab lifecycle and readiness surfaces come from `_LAB_START_STEPS`,
  `LabResult`, `StartupOutcome`, and `StartupDiagnostic`;
- runtime snapshots come from `RangeSnapshot.to_dict()` and the endpoint
  registry boundary in ADR-036;
- run archives come from `LocalRunStore` and its redacting JSON/JSONL write
  boundary.

A machine-readable inventory must remain a narrow audit manifest. Fields cover legacy identity, canonical source, owner category, target, validation evidence, and blocking follow-up. It must not duplicate scenario models, RAES types, Compose parsing, secret classification, readiness classification, or exception/result envelopes.

## RAES Backend Integration Guardrails

APTL's RAES backend target is an adapter over existing APTL control-plane
boundaries. The implementation must not bypass those boundaries just because
the caller is RAES.

- RAES SDL documents enter through the RAES reference parser and semantic
  validators; APTL does not perform structural revalidation of RAES SDL with
  local models.
- RAES runtime work enters APTL through the RAES `RuntimeModel`,
  `ExecutionPlan`, backend manifest, operation receipt/status, and runtime
  snapshot contracts. The APTL-side target adapts those contracts to existing
  APTL owners rather than inventing a parallel runtime manager.
- Docker, container, and host inventory operations continue through
  `DeploymentBackend`; no RAES adapter code should call raw Docker or parse
  Compose output directly.
- Lab start/stop behavior continues to produce `LabResult` and structured
  startup diagnostics at APTL-facing edges. RAES-facing failures are translated
  into RAES diagnostics or operation-status envelopes at the adapter boundary;
  do not add an `AcesAptlError` hierarchy or expose raw backend exception text.
- Generated config, SOC TLS material, seed outputs, and any other
  secret-bearing runtime artifacts remain under the ADR-028 / ADR-034 generated
  artifact model. The backend manifest and parity inventory must not embed
  `.env` values, private key material, API tokens, cookies, or rendered config.
- Snapshot, status, telemetry, CLI/API output, run archives, and conformance
  artifacts remain subject to ADR-029 redaction. New RAES status or run
  evidence writers must reuse `RangeSnapshot.to_dict()` and `LocalRunStore`
  JSON/JSONL redaction boundaries where those artifacts cross APTL
  serialization.
- Published backend capability stays profile-named and contract-validated:
  `create_aptl_manifest()` plus the static/live conformance gates define the
  current claim. Any future profile promotion must update the manifest,
  runtime target components, conformance gates, and ADR wording together.

The extensibility seam is the RAES backend capability profile plus a small
backend realization map from RAES runtime resource kinds to existing APTL
control-plane owners. Do not make TechVault-specific branches the public
adapter contract; TechVault is the parity proving case for the supported
expressivity class, not the backend's type system.

## Legacy Cleanup Reconciliation

Issue #530 is a post-cutover reconciliation, not a new scenario-authoring
surface. It must leave one active path:

- Public runtime selection flows through `scenarios/catalog.json`,
  `aptl.core.scenario_catalog.resolve_scenario_selection()`,
  `raes.parse_sdl_file`, `RuntimeManager.plan()`, and
  `aptl.backends.raes.start_raes_scenario()`.
- Backend capability and runtime handoff flow through `create_aptl_manifest()`,
  `create_aptl_runtime_target()`, `AptlProvisioner`, `AptlOrchestrator`,
  `AptlEvaluator`, `AptlParticipantRuntime`, RAES diagnostics, and
  `DeploymentBackend`.
- Legacy `scenarios/*.yaml`, `aptl.core.sdl`, `aptl.core.scenarios`, and
  `ScenarioDefinition` references may remain only when explicitly marked as
  historical or reference-only and unreachable from catalog/default startup,
  static/live gates, and runtime loaders. Unlabeled references are drift.
- If any legacy local SDL code is intentionally retained, this ADR and the GRC
  workflow platform status must say why. It must not parse, validate, or model RAES SDL,
  and it must not reintroduce APTL-local SDL semantics as a source of truth.
- The parity inventory and historical preflight notes remain audit/history
  surfaces. They must not become runtime inputs, alternate schema authorities,
  or justification for keeping duplicate parser, validator, exception, or
  readiness layers alive.
- The cleanup regression target is that
  `rg "aptl.core.sdl|ScenarioDefinition|scenarios/.*\\.yaml" docs src tests scenarios`
  returns either no hits or only hits carrying clear historical/reference-only
  labels.

## Historical Migration Plan

The migration split into a multi-PR prep phase and a single-PR cutover. This
section records the original adoption sequence; current cleanup work is governed
by the Legacy Cleanup Reconciliation section above.

### Phase A—Prep (multiple PRs, parallel RAES path, non-default)

1. Add `raes` as an APTL Python dependency.
2. Implement a RAES `RuntimeTarget` against the existing lab
   orchestration. Land it as a *parallel* path; existing CLI entrypoints
   continue to use `aptl.core.sdl`.
3. Publish APTL's `backend-manifest-v2` under an APTL-side contracts
   path.
4. Wire `raes conformance backend --profile orchestration-capable` as an
   **advisory** check (non-blocking) so drift is visible during Phase A.
5. Author `scenarios/techvault.sdl.yaml` in RAES SDL.

### Parity Gate

See dedicated section above. Hard prerequisite to Phase B.

### Phase B—Cutover (single PR)

Lands in one PR:

- Default public startup scenario flips to
  `scenarios/techvault-operational.sdl.yaml`; the detailed
  `scenarios/techvault.sdl.yaml` remains the inventory/parity evidence
  artifact.
- `aptl lab` and CLI entrypoints route through RAES `RuntimeManager`.
- `scenarios/*.yaml` moves to `scenarios/archive/` with a README marking
  the directory strictly reference-only (not loaded by any runtime path).
- `aptl.core.sdl` deleted.
- `aptl.core.scenarios` Pydantic models deleted; the module remains only for
  shared session/continuity exception types.
- `raes conformance backend --profile orchestration-capable` switches from
  advisory to enforced (pre-push gate).
- GRC workflow platform reconciliation in the same PR:
  - DSL-001 → DEPRECATED
  - SCN-001 → DEPRECATED
  - DSL-002..DSL-009 → DEPRECATED (no per-item cross-links)
  - RTE-001 statement updated to consume the RAES `RuntimeModel`
  - Follow-on issues #311 and #312 confirmed open and linked

SCN-010 itself is ACTIVE from creation; the cutover does not flip its
status.
- Existing traceability links from the deprecated requirements are
  preserved as historical record; new links from SCN-010 are created
  during the same PR.

The cutover PR is large by necessity and will not be split. Splitting
would leave APTL with a half-flipped default surface or inconsistent
deprecations across releases.

## Consequences

### Positive

- Cross-backend reproducibility becomes demonstrable: the same RAES SDL
  document can run on APTL's lab and on any other conforming backend.
- DSL-001 and DSL-002..DSL-009 fold into the RAES roadmap; APTL stops
  paying duplicate grammar/parser/validation/tooling costs.
- APTL gains RAES's existing tooling (`resolve`, `verify-imports`,
  `publish`, lockfiles, OCI module distribution, MCP server) for free.
- RAES gains its first real-world conformant backend—the research
  story.
- Run provenance gains typed clock/synchronization/pacing surfaces from
  RAES contracts, supporting reproducibility across realizations.

### Negative / costs

- Existing scenarios move to the archive rather than receive a local schema rewrite. The original migration expected one move after RAES TechVault parity.
- APTL now depends on the `raes` Python package; version pinning and
  upstream-coordination become real workflow concerns.
- Backend conformance becomes a pre-push gate; failing conformance
  blocks merge. This is the intended quality contract.
- DSL-001 / SCN-001 deprecation cascades through the GRC workflow platform
  traceability—every link from those requirements must be reconciled
  in the cutover PR.

## Alternatives Considered

1. **Keep APTL's in-tree SDL, mirror RAES grammar.** Rejected: defeats cross-backend reproducibility. LilRAE would become a manually synchronized dialect without machine-readable conformance.
2. **Adopt RAES SDL but skip the backend conformance suite.** Rejected:
   without conformance, APTL is not a demonstrable RAES backend, and the
   research claim collapses to "we use RAES syntax," not "RAES portability
   holds against a real range".
3. **Defer adoption until RAES reaches 1.0.** Rejected: RAES needs APTL
   as a real backend to drive contract design (`backend-manifest-v2`,
   profile splits, evaluator contracts already reflect that). Delaying
   makes both projects harder; co-evolution is the design assumption.

## Related Requirements

- Supersedes: DSL-001 (Formal Scenario Specification Language),
  SCN-001 (Declarative YAML Scenario Specifications)—both transitioned
  to DEPRECATED at cutover
- Deprecates at cutover: DSL-002 through DSL-009—no per-item
  cross-links; bulk DEPRECATED transition
- Updates at cutover: RTE-001 (Scenario Runtime Engine)—input source
  changes to RAES `RuntimeModel`
- Implements: SCN-010 (RAES SDL as APTL's Canonical Scenario Authoring
  Surface)

## Related Issues

- Parent: [#310](https://github.com/Brad-Edwards/aptl/issues/310)—
  Adopt RAES SDL as APTL's canonical scenario authoring surface
- Follow-on: [#311](https://github.com/Brad-Edwards/aptl/issues/311)—
  Upgrade APTL backend conformance to `orchestration-capable` profile
- Follow-on: [#312](https://github.com/Brad-Edwards/aptl/issues/312)—
  Upgrade APTL backend conformance to `orchestration-evaluation` profile
