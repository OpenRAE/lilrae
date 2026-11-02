# Issue #1017 TechVault Bridge Retirement Preflight

Issue #1017, including its third-party family acceptance criterion, is the
contract. Retire the temporary behavior through released RAE contracts; do not
turn it into an extensible policy or attestation service. This note supplements
the [#992 compatibility guardrail](issue-992-backend-observability-ownership-preflight.md#compatibility-cutover-guardrail)
and the [family adapter contract](family-adapter-contract.md). It records
boundaries and acceptance risks, not an implementation plan. No new ADR is
needed: portable semantics, native observation, and installed adapter ownership
already have owners under ADR-046, ADR-047 and ADR-053.

## Baseline and release condition

Inspection at `bd13dea3` found metadata floors of `raes>=10.1.0,<11` and
`raes-env-packs>=6.5.1,<7`; the lock, runtime export and local installed
distributions select 10.1.0 and 6.5.1. The qualified TechVault identity is
version `0.1.3`, declared in `aptl_techvault/pack_identity.py`. The older #992
release numbers and plan size are historical, not the current qualification.

A read-only compile/plan probe used the installed TechVault SDL, synthetic flag
bindings, `compile_scenario_runtime_model()`, `plan()` and
`create_aptl_manifest()`, bypassing all local planning adjustments. It produced
2,124 requirements, 2,068 authority entries and 132 provisioning resources.
The provisioning plan and compiled requirements both fit the released normal
`PLAN_VALUE_LIMITS` of 262,144 nodes; snapshots retain their separate 65,536-node
bound. Most configuration requirements now have no prescribed observation
source; effective process limits still require guest observation.

That probe still reported **377 under-observed open requirements**, covering
13 kinds on 29 nodes: masked/read-only paths, publish-all-ports, mail services,
network domainname/endpoints/hostname, CPU/swap/PID limits, processes, scheduled
jobs and SSH servers. The existing bridge's delegation removes these support
errors. Capture-offer and exact-artifact diagnostics also occurred because the
probe supplied neither capture nor artifact availability context. This is
evidence that deletion alone is insufficient, not a complete admission or live
realization qualification, nor proof that another release is unavailable.

The adopted release and actual manifest must admit the complete unchanged
compiler output through public contracts, with real artifact/capture context.
Unsupported compiler-generated defaults need owner-supported semantics or real
backend support. Do not fix this by dropping requirements, changing authority,
inflating the manifest or recreating delegation locally. If released contracts
cannot cover the remaining needs, report the specific upstream gap. A version
bump, larger upstream plan budget or merged upstream issue alone does not
satisfy retirement.

## Ownership and retirement boundaries

| Existing owner | Boundary to preserve |
| --- | --- |
| `backends/raes_planning_compat.py`, `_raes_planning_entry.py`, `_raes_planning_adjustment.py` | Compile and plan once through public RAE APIs. Retire requirement-strength, explicitness, constraint and delegation rewrites and the process-global `_runtime_value_limits` mutation. Preserve parameters, profile authority, artifact availability, run/instantiation scope and participant diagnostics. Planning stays free of deployment effects. |
| `AptlRuntimeManager`, `_raes_start_run.py`, `raes.py` | Keep one live runtime owner per run. The class in the compatibility module also captures native evidence on apply, inventory refresh and evaluation; its filename is not a reason to delete those behaviors or substitute another runtime. |
| `raes_runtime_attestation.py`, `_raes_observation_ordering.py`, `raes_observation.py` | Retire release/projection tables and release-specific value/order transformations. Preserve generic native readback, catalog-image observation, content verification and qualified adapter observation. `observe_scenario_runtime_concerns()` currently sits inside `_add_techvault_runtime_attestations()`; it must survive retirement of that wrapper. Collection equality belongs to released RAE semantics: inventory identity, duplicate membership and ordered commands must not be conflated. |
| `_raes_manifest_realization.py`, `raes_diagnostics.py` | Real native capabilities and their disclosures must stand independently of `DAEMON_READBACK_RUNTIME_CONCERNS`, currently aliased from the compatibility decision vocabulary. Retire only unsupported compatibility claims. Presence, configuration coverage and actual daemon/guest source remain distinct; a concern-name whitelist is not proof. |
| `aptl_techvault/{planning_compatibility,runtime_parameters,study,pack_identity}.py` | Remove compatibility effects and imports of attestation pins, including the study digest dependency. Keep legitimate exact release qualification and fresh runtime-owned parameters. Removing projection tables does not mean removing pack integrity or installed adapter provenance. |

The public `aptl.scenario_planning_compatibility` seam is currently mandatory in
`scenario_family.family_capabilities()`, both bundled registrations and
independent adapter fixtures. Deleting the seam requires a consistent change to
the public family contract, including `scenario_planning_compatibility_discovery.py`
result validation, registrations, documentation and installed adapter
qualification. Do not delete only the TechVault entry point and break every
family, or retain operative policy fields as a future extension mechanism.
[ADR-066](../adrs/adr-066-runtime-readback-reports-realized-state.md) deletes
the seam in that consistent form. Core no longer reads the group, so an
installed decision has no effect and RAES judges the unchanged plan.

Native observations, SEM-218 provenance, runtime materialization attestations
and experiment capture evidence serve different purposes. In particular,
`lilrae_materialization_reporting.py`, `LilraeMaterializationArchive`, native
creation/descendant receipts and `LilraeRuntimeEvidence` are not the temporary
projection bridge. Preserve their operation/run/envelope binding and evidence
loss reporting. Image/content identity corroborates an implementation; it does
not establish live application state, prove arbitrary configuration, grant host
authority or manufacture a guest observation.

## Cross-cutting gates

Paths below are relative to `src/aptl/` unless otherwise stated. These owners
remain mandatory even when the changed artifact passes its local validator.

| Layer and canonical incumbent | Required behavior |
| --- | --- |
| Authentication and installed code | This change needs no listener or auth option. Existing API callers retain `api/main.py`, `deps.verify_token`, `WebAuthSettings` and `middleware/bff.py` Host/session/CSRF checks. `scenario_family`, purpose-specific discovery and `_lilrae_family_release_set` retain exact selectors, one distribution/version, duplicate/load/result failure handling and release compatibility checks before effects. A validated pack cannot install Python; installed adapters are trusted executable code, not a sandbox. |
| Source and parser ingress | Reuse `ScenarioSourceConfig`, `resolve_scenario_bundle()`, `env_pack_bundle()`, `_pack_staging`, upstream pack/content-manifest validators and `utils/pathsafe.py`. Preserve bounded private staging, no-follow contained reads and digest-bound bytes. RAE owns SDL parsing, explicitness, compilation and trial instantiation. No second parser/schema, directory-name identity, pack-local `.env` authority or edited installed pack bytes. |
| Compiler, capability and runtime contracts | Use public RAE requirement/authority, observation, manifest and realization-envelope models and validators. Retain `create_aptl_manifest()`, `build_aptl_realization_envelope()`, `AptlProvisioner.validate()`, `interpret_provisioning_plan()` and runtime SEM-218 admission/comparison. Required scope/source, constraints, closed scopes and explicit empty values cannot be weakened to obtain a plan. Runtime input, snapshot, result-details and materialization limits remain separate finite gates; no monkeypatches, private dependency globals, computed budget inflation or truncated authority/evidence. |
| Config and environment shapes | Keep `AptlConfig` and nested `extra="forbid"` models. No per-pack budget or observation-policy config. Reuse `EnvironmentGrant`, `EnvVars`, placeholder checks, `_credential_sources.py`, `_environment_bindings.py` and `_compose_environment.py`. Bind sources to the exact pack, consumer and variable; generated `value_from` remains node-bound, and external `secret_fixture` requires OPEN environment authority. Recheck changed consumers for each trial. No ambient same-name secret lookup. |
| Secret-safe observation and results | Reuse `raes_runtime_observation.py`, guest observers, `_runtime_concern_disclosure._record/_disclose`, public `scenario_runtime_hooks.disclose_runtime_concern()` and `_scenario_startup_runtime` result checks. Protected values remain presence-only; sourced fixture secrets must not gain guessable commitments. Preserve `snapshot_after_apply()`, `_raes_apply_reporting.closed_credential_result()` and RAE's credential-bearing result sanitizer: values under admitted observation authority differ from plan-owned residual fields; free-form details stay closed. Source-image evidence stays outside credential-bearing entry payloads. |
| Host authority and process exposure | `DeploymentBackend`, `runtime_authority.py`, deployment admission, `WorkspaceOwnership`/`ResourceReceipt`, verified resource resolution and lifecycle locks continue to govern mounts, capabilities, networks, daemon endpoints and observation/cleanup targets. No added Docker socket, broad inspect access, guest agent or privilege grant to replace the bridge. Use existing bounded backend operations and `utils/curl_safe.py`; credentials travel through existing private files/stdin, never argv, URLs, shell tracing or logs. `_realization_primitives.environment_file_line()` must carry values exactly or refuse them; Compose retains its filtered client environment. |
| Trial/adapter boundary | Reuse `QualifiedFamilyTarget`, `FamilyTrialInput`, `AdmittedFamilyTrial` and detached snapshots. The admitted snapshot is the per-trial source of concerns; family/pack qualification does not authorize a rewrite. Keep `ScenarioStartupSelection`, scoped `AdmittedRuntimeOperations` and provider drift checks through retry/reset/finalization. Its inspect projection intentionally excludes environment values: do not widen it to raw `Config.Env` for convenience. |
| Persistence and evidence | Reuse `RunStorageBackend`/`LocalRunStore`, `LilraeMaterializationArchive`, `LilraeRuntimeEvidence`, capture registry/source/outcome types and ADR-050 sealing. Retain run/attempt identity, no-follow bounded regular-file access, private modes, create-once writes and finalization locks. Original owner bytes and digests survive unchanged in protected storage. Preserve restricted capture visibility and loss/clock/observer-effect disclosures; do not redact and reseal identity-bearing bytes or rewrite historical archives. |
| Errors and observability | Reuse RAE `Diagnostic`/`ApplyResult`, `raes_diagnostics.diagnostic()`/`render_raes_diagnostics()`, `LabResult`, existing deployment/provider errors and `experiment/errors.py`; no parallel exception hierarchy or formatter. Missing/unreadable/malformed observations fail closed and stay distinct from proven empty state. Use bounded codes, safe identity, counts and durations. `get_logger()` does not sanitize arbitrary arguments: retain `utils/redaction.py`, safe snapshot/provenance projections and `core/telemetry_export.RedactingSpanExporter`. Raw exceptions, Pydantic inputs, inspect data, config, stdout/stderr and credentials must not escape into CLI/API/log/span envelopes. |
| Dependency and delivery closure | Keep `pyproject.toml`, `uv.lock` and applicable hashed `requirements/*.txt` consistent through `.pre-commit-ci.yaml` lock/export owners. No editable/VCS/local upstream substitute or manual hash edits. `hatch_build.py`, `_asset_manifest.py`, container/service builds and appliance/offline wheelhouses must consume the same qualified closure. Retain `tools/check_pack_boundary.py` and remove obsolete entries from `.gc/pack-ownership.json` when their source is retired, without widening exceptions. |

## Extensibility and acceptance evidence

The variation seam is the existing **admitted trial snapshot plus real native
observer inputs**, not a release digest mapped to concern values. Reuse generic
daemon/guest observers for backend facts and qualified startup observers for
application interpretation that the family owns. A new supported concern or another
trial may select a different native source through released contracts; it must
not require another release table, compiler adapter, selector enum or observer
registry. Source provenance must describe the observation actually performed.

The independent installed family in `tests/fixtures/family_adapter`, the
structural family in `tests/fixtures/structural_family` and
`test_family_adapter_contract.py`/`test_structural_factorial_family.py` are the
existing qualification owners. Current structural qualification demonstrates
admission and verification; it does not prove native realization. #1017 needs
the same independently installed family release to vary concerns across trials
and realize through the ordinary backend path without projection pins or
rewrites. Keep exact pack qualification; it is not a release-keyed evidence
table. Confirm trial isolation, provider provenance and negative missing-evidence
behavior across those variations.

Preserve behavioral evidence in `test_raes_runtime_observation.py`,
`test_raes_observation.py`, `test_raes_backend.py`,
`test_raes_credential_result_contract.py`, `test_raes_native_evidence_truth.py`
and `test_lilrae_runtime_evidence.py`. Retire only shim-specific assertions in
planning/attestation tests. Required distinctions include OPEN choices versus
EXACT/CONSTRAINED/CLOSED authority, omitted versus explicitly empty fields,
backend-selected defaults, ordered versus identity collections, malformed or
missing evidence, foreign/stale resource proof, credential canaries and accurate
author/processor/backend provenance. A full-size plan must pass without global
overrides, while oversized inputs still fail. Capture failure cannot silently
become successful evidence, and failure/retry must not create another runtime
owner or reuse stale observations.

Use `.ground-control.yaml`, `.gc/plan-rules.md`,
`tools/run-targeted-tests.sh` and staged `pre-commit run` for local checks.
`tools/ci/select_checks.py` and `.github/workflows/checks.yml` own full suites,
conformance, installed-artifact checks and clean installed-lab qualification.
Dependency adoption and actual native behavior require those existing lanes;
mocked readback or the compile probe above cannot certify them. Preserve
historical evidence notices and update current compatibility guidance at cutover.

## Non-goals

No issue implementation in this preflight. The delivery introduces no new
portable language, schema, comparison engine, policy/attestation framework,
plugin system, exception hierarchy, persistence service or workflow. It does
not redesign authentication, credential sourcing, capture apparatus, runtime
descendant reporting or sealed history. Do not weaken tests, claim support from
planned values, automatically install third-party code, or expand privilege to
make the original scenario pass. Versioning/publication remain with the normal
release workflow; no manual version or CHANGELOG edits.
